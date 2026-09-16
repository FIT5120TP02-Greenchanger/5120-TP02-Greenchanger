import { useEffect, useState } from 'react'
import SpeciesIntro from './steps/SpeciesIntro'
import SpeciesList from './steps/SpeciesList'
import SpeciesDetail from './steps/SpeciesDetail'
import Impact from './steps/Impact'
import Guidance from './steps/Guidance'
import TreeChoosing from '../comparing/TreeChoosing'
import TreeCompare from '../comparing/TreeCompare'
import { fetchSpecies, simulateScenario, PREVIEW_AGE_YEARS } from '../../services/trees'

import styles from './TreePlantingFlow.module.css'
const STEPS = { INTRO: 'intro', LIST: 'list', DETAIL: 'detail', IMPACT: 'impact', GUIDANCE: 'guidance', CHOOSE: 'choose', COMPARE: 'compare' }
const BACK_TARGET = {
    [STEPS.LIST]: STEPS.INTRO, [STEPS.DETAIL]: STEPS.LIST,
    [STEPS.IMPACT]: STEPS.DETAIL, [STEPS.GUIDANCE]: STEPS.IMPACT, [STEPS.CHOOSE]: STEPS.IMPACT , [STEPS.COMPARE]: STEPS.CHOOSE
}

const DEFAULT_SIZE = 'Small'

export default function TreePlantingFlow({ lot, position, onApply, onExit, nTrees, canopyM2, viewM2 }) {
    const [step, setStep] = useState(STEPS.INTRO)
    const [selectedSpecies, setSelectedSpecies] = useState(null)
    const [selectedSize, setSelectedSize] = useState(DEFAULT_SIZE)
    const [appliedScenario, setAppliedScenario] = useState(null)
    const [compareArray, setCompareArray] = useState([])

    const [species, setSpecies] = useState([])
    const [limitations, setLimitations] = useState(null)
    const [speciesError, setSpeciesError] = useState(null)
    const [applying, setApplying] = useState(false)

    useEffect(() => {
        let cancelled = false
        resetFlow()
        setSpeciesError(null)
        fetchSpecies(lot?.address)
            .then((data) => {
                if (cancelled) return
                // Only species with a trained growth model can give real canopy figures.
                setSpecies((data.species || []).filter((s) => s.has_growth_model))
                setLimitations(data.limitations || null)
            })
            .catch(() => { if (!cancelled) setSpeciesError("Could not load tree species.") })
        return () => { cancelled = true }
    }, [lot?.address]) // eslint-disable-line react-hooks/exhaustive-deps
    console.log(species)
    function resetFlow(nextStep = STEPS.INTRO) {
        setSelectedSpecies(null); setSelectedSize(DEFAULT_SIZE); setAppliedScenario(null); setStep(nextStep)
    }
    function goBack() { setStep(BACK_TARGET[step] ?? STEPS.INTRO) }
    function handleSelectSpecies(species) {
        setSelectedSpecies(species); setSelectedSize(DEFAULT_SIZE); setStep(STEPS.DETAIL)
    }
    function handleViewDetail() {
        if (selectedSpecies) setStep(STEPS.DETAIL)
    }

    // The moment the tree actually gets planted — position was already fixed in step 3.
    async function handleApply(growth) {
        if (!selectedSpecies || !selectedSize || !growth) return

        setApplying(true)
        try {
            const result = await simulateScenario({
                inputs: {
                    quantity: 1,
                    projected_canopy_per_tree_m2: {
                        minimum: growth.canopy_m2_min,
                        maximum: growth.canopy_m2_max,
                    },
                    maturity_horizon_years: PREVIEW_AGE_YEARS,
                    survival_probability: { minimum: 0.5, maximum: 1.0 },
                    site_suitability_factor: { minimum: 0.5, maximum: 1.0 },
                    overlap_factor: { minimum: 1.0, maximum: 1.0 },
                    site_area_m2: lot?.areaM2 ?? 100, // fall back to their own example value if unknown
                },
            })
            const scenario = {
                species: selectedSpecies,
                size: selectedSize,
                impact: result,
                growth,
                years: PREVIEW_AGE_YEARS,
                position,
            }
            console.log('Scenario: ', scenario);
        setAppliedScenario(scenario)
            onApply?.(scenario)
            setStep(STEPS.IMPACT)
        } catch {
            setSpeciesError("Could not simulate that scenario. Try again.")
        } finally {
            setApplying(false)
        }
    }
    function renderStep() {
        switch (step) {
            case STEPS.INTRO:
                return <SpeciesIntro onExplore={() => setStep(STEPS.LIST)} onExit={onExit} nTrees={nTrees} canopyM2={canopyM2} viewM2={viewM2} canExplore={!!position} />
            case STEPS.LIST:
                return <SpeciesList species={species} error={speciesError} limitation={limitations} selectedSpecies={selectedSpecies} onSelect={handleSelectSpecies} onViewDetail={handleViewDetail} onBack={goBack} onExit={onExit} />
            case STEPS.DETAIL:
                return <SpeciesDetail species={selectedSpecies} size={selectedSize} setCompareArray={setCompareArray} onSizeChange={setSelectedSize} onApply={handleApply} applying={applying} onBack={goBack} onExit={onExit} />
            case STEPS.IMPACT:
                return <Impact scenario={appliedScenario} onViewGuidance={() => setStep(STEPS.GUIDANCE)} onCompare={() => setStep(STEPS.CHOOSE)} onBack={goBack}/>
            case STEPS.GUIDANCE:
                return <Guidance onBack={goBack} onStartAgain={() => resetFlow()}/>
            case STEPS.CHOOSE:
                return <TreeChoosing species={species.filter((s) => s !== selectedSpecies)} selectedSpecies={selectedSpecies} onCompareTree={() => setStep(STEPS.COMPARE)} compareArray={compareArray} setCompareArray={setCompareArray} onBack={goBack}/>
            case STEPS.COMPARE:
                return <TreeCompare compareArray={compareArray} onBack={goBack} onViewGuidance={() => setStep(STEPS.GUIDANCE)}/>
            default:
                return null
        }
    }
    return <div className={styles['panel-page']}>
        {renderStep()}
    </div>
}