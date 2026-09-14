import { useEffect, useState } from 'react'
import SpeciesIntro from './steps/SpeciesIntro'
import SpeciesList from './steps/SpeciesList'
import SpeciesDetail from './steps/SpeciesDetail'
import Impact from './steps/Impact'
import Benefits from './steps/Benefits'
import Guidance from './steps/Guidance'
import {calculatePlantingImpact} from '../../utils/plantingImpact'
import { TREE_SPECIES } from '../../data/treeSpecies'

const STEPS = { INTRO: 'intro', LIST: 'list', DETAIL: 'detail', IMPACT: 'impact', BENEFITS: 'benefits', GUIDANCE: 'guidance' }
const BACK_TARGET = {
    [STEPS.LIST]: STEPS.INTRO, [STEPS.DETAIL]: STEPS.LIST,
    [STEPS.IMPACT]: STEPS.DETAIL, [STEPS.BENEFITS]: STEPS.IMPACT, [STEPS.GUIDANCE]: STEPS.BENEFITS,
}

export default function TreePlantingFlow({ lot, position, onApply, onExit, nTrees, canopyM2, viewM2 }) {
    const [step, setStep] = useState(STEPS.INTRO)
    const [selectedSpecies, setSelectedSpecies] = useState(null)
    const [selectedSize, setSelectedSize] = useState(null)
    const [appliedScenario, setAppliedScenario] = useState(null)

    useEffect(() => { resetFlow() }, [lot?.address]) // eslint-disable-line react-hooks/exhaustive-deps

    function resetFlow(nextStep = STEPS.INTRO) {
        setSelectedSpecies(null); setSelectedSize(null); setAppliedScenario(null); setStep(nextStep)
    }
    function goBack() { setStep(BACK_TARGET[step] ?? STEPS.INTRO) }
    function handleSelectSpecies(species) {
        setSelectedSpecies(species); setSelectedSize(null); setStep(STEPS.DETAIL)
    }
    function handleChangeSpecies() { resetFlow(STEPS.LIST) }

    // The moment the tree actually gets planted — position was already fixed in step 3.
    function handleApply() {
        const impact = calculatePlantingImpact({ species: selectedSpecies, size: selectedSize, lot })
        const scenario = { species: selectedSpecies, size: selectedSize, impact, position }
        setAppliedScenario(scenario)
        onApply?.(scenario)      // creates the tree in MapView's simulatedTrees
        setStep(STEPS.IMPACT)    // then just show the recap
    }

    switch (step) {
        case STEPS.INTRO:
            return <SpeciesIntro onExplore={() => setStep(STEPS.LIST)} onExit={onExit} nTrees={nTrees} canopyM2={canopyM2} viewM2={viewM2} />
        case STEPS.LIST:
            return <SpeciesList species={TREE_SPECIES} onSelect={handleSelectSpecies} onBack={goBack} onExit={onExit} />
        case STEPS.DETAIL:
            return <SpeciesDetail species={selectedSpecies} size={selectedSize} onSizeChange={setSelectedSize} onApply={handleApply} onBack={goBack} onExit={onExit} />
        case STEPS.IMPACT:
            return <Impact scenario={appliedScenario} onChangeSpecies={handleChangeSpecies} onViewBenefits={() => setStep(STEPS.BENEFITS)} onBack={goBack} onExit={onExit} />
        case STEPS.BENEFITS:
            return <Benefits scenario={appliedScenario} onBack={goBack} onViewGuidance={() => setStep(STEPS.GUIDANCE)} onExit={onExit} />
        case STEPS.GUIDANCE:
            return <Guidance onBack={goBack} onStartAgain={() => resetFlow()} onExit={onExit} />
        default:
            return null
    }
}