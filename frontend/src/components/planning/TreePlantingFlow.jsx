import { useEffect, useState, useCallback } from 'react'
import SpeciesIntro from './steps/SpeciesIntro'
import SpeciesList from './steps/SpeciesList'
import SpeciesDetail from './steps/SpeciesDetail'
import Impact from './steps/Impact'
import Guidance from './steps/Guidance'
import TreeChoosing from '../comparing/TreeChoosing'
import TreeCompare from '../comparing/TreeCompare'
import PreferredScenario from '../comparing/PreferredScenario'
import { fetchSpecies, fetchGrowth, fetchCosts, simulateScenario, PREVIEW_AGE_YEARS } from '../../services/trees'

import styles from './TreePlantingFlow.module.css'
const STEPS = {
    INTRO: 'intro', LIST: 'list', DETAIL: 'detail', IMPACT: 'impact', GUIDANCE: 'guidance',
    CHOOSE: 'choose', COMPARE: 'compare', PREFERRED: 'preferred',
}
const BACK_TARGET = {
    [STEPS.LIST]: STEPS.INTRO, [STEPS.DETAIL]: STEPS.LIST,
    [STEPS.IMPACT]: STEPS.DETAIL, [STEPS.GUIDANCE]: STEPS.IMPACT,
    [STEPS.CHOOSE]: STEPS.IMPACT, [STEPS.COMPARE]: STEPS.CHOOSE,
    [STEPS.PREFERRED]: STEPS.COMPARE,
}

const DEFAULT_SIZE = 'Small'

export default function TreePlantingFlow({ lot, position, onApply, onExit, nTrees, canopyM2, viewM2 }) {
    const [step, setStep] = useState(STEPS.INTRO)
    const [selectedSpecies, setSelectedSpecies] = useState(null)
    const [selectedSize, setSelectedSize] = useState(DEFAULT_SIZE)
    const [appliedScenario, setAppliedScenario] = useState(null)
    const [compareArray, setCompareArray] = useState([])

    // One entry per species in compareArray, keyed by species_key: { species, size,
    // growth, costs, impact, loading, error }. Lives here (not in TreeCompare) so it
    // survives navigating to the Preferred step and back without refetching.
    const [comparisonRows, setComparisonRows] = useState({})
    const [preferredKey, setPreferredKey] = useState(null)

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
                setSpecies((data.species || []).filter((s) => s.has_growth_model))
                setLimitations(data.limitations || null)
            })
            .catch(() => { if (!cancelled) setSpeciesError("Could not load tree species.") })
        return () => { cancelled = true }
    }, [lot?.address]) // eslint-disable-line react-hooks/exhaustive-deps

    function resetFlow(nextStep = STEPS.INTRO) {
        setSelectedSpecies(null); setSelectedSize(DEFAULT_SIZE); setAppliedScenario(null)
        setCompareArray([]); setComparisonRows({}); setPreferredKey(null)
        setStep(nextStep)
    }
    function goBack() { setStep(BACK_TARGET[step] ?? STEPS.INTRO) }
    function handleSelectSpecies(species) {
        setSelectedSpecies(species); setSelectedSize(DEFAULT_SIZE); setStep(STEPS.DETAIL)
    }
    function handleViewDetail() {
        if (selectedSpecies) setStep(STEPS.DETAIL)
    }

    const runImpactSimulation = useCallback((growth) => simulateScenario({
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
            site_area_m2: lot?.areaM2 ?? 100,
        },
    }), [lot?.areaM2])

    // The moment the tree actually gets planted — position was already fixed earlier.
    async function handleApply(growth, costs) {
        if (!selectedSpecies || !selectedSize || !growth) return
        setApplying(true)
        try {
            const impact = await runImpactSimulation(growth)
            const scenario = {
                species: selectedSpecies, size: selectedSize,
                impact, growth, costs, years: PREVIEW_AGE_YEARS, position,
            }
            setAppliedScenario(scenario)
            onApply?.(scenario)
            setStep(STEPS.IMPACT)
        } catch {
            setSpeciesError("Could not simulate that scenario. Try again.")
        } finally {
            setApplying(false)
        }
    }

    // Used by the comparison step: there's no SpeciesDetail mounted for the species being
    // compared, so growth/costs have to be fetched here before simulating impact.
    const fetchScenarioFor = useCallback(async (targetSpecies, size) => {
        const [growth, costsRaw] = await Promise.all([
            fetchGrowth({ species: targetSpecies.scientific_name, size, years: PREVIEW_AGE_YEARS }),
            fetchCosts({ treeType: targetSpecies.common_name }),
        ])
        const costs = Array.isArray(costsRaw) ? costsRaw[0] : costsRaw
        const impact = await runImpactSimulation(growth)
        return { species: targetSpecies, size, growth, costs, impact }
    }, [runImpactSimulation])

    function handleChoosePreferred(key) {
        setPreferredKey(key)
        setStep(STEPS.PREFERRED)
    }
    function handleRemovePreferred() {
        setPreferredKey(null)
        setStep(STEPS.COMPARE)
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
                return <Impact scenario={appliedScenario} onViewGuidance={() => setStep(STEPS.GUIDANCE)} onCompare={() => setStep(STEPS.CHOOSE)} onBack={goBack} />
            case STEPS.GUIDANCE:
                return <Guidance onBack={goBack} onStartAgain={() => resetFlow()} />
            case STEPS.CHOOSE:
                return <TreeChoosing species={species.filter((s) => s !== selectedSpecies)} selectedSpecies={selectedSpecies} onCompareTree={() => setStep(STEPS.COMPARE)} compareArray={compareArray} setCompareArray={setCompareArray} onBack={goBack} />
            case STEPS.COMPARE:
                return (
                    <TreeCompare
                        compareArray={compareArray}
                        appliedScenario={appliedScenario}
                        rows={comparisonRows}
                        onRowsChange={setComparisonRows}
                        fetchScenarioFor={fetchScenarioFor}
                        canopyM2={canopyM2}
                        viewM2={viewM2}
                        preferredKey={preferredKey}
                        onChoosePreferred={handleChoosePreferred}
                        onBack={() => setStep(STEPS.CHOOSE)}
                    />
                )
            case STEPS.PREFERRED:
                return (
                    <PreferredScenario
                        compareArray={compareArray}
                        rows={comparisonRows}
                        preferredKey={preferredKey}
                        canopyM2={canopyM2}
                        viewM2={viewM2}
                        onChangePreference={() => setStep(STEPS.COMPARE)}
                        onRemovePreference={handleRemovePreferred}
                        onBack={() => setStep(STEPS.COMPARE)}
                        onViewGuidance={() => setStep(STEPS.GUIDANCE)}
                    />
                )
            default:
                return null
        }
    }
    return <div className={styles['panel-page']}>
        {renderStep()}
    </div>
}