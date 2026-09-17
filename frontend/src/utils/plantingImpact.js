import { TREE_SIZES } from '../hooks/simulation';


const BASE_RATES_PER_M2_PER_YEAR = {
    carbonSequestration: 0.65,     // kg CO2
    stormwaterInterception: 0.03,  // m3
    energySavings: 1.1,            // kWh (shading/cooling)
    airQualityImprovement: 0.004,  // kg PM10
};

export function calculatePlantingImpact({ species, size }) {
    const radiusM = TREE_SIZES[size]?.radiusM ?? TREE_SIZES.Medium.radiusM;
    const canopyM2 = Math.PI * radiusM ** 2;
    const factor = species?.benefitFactor ?? 1;

    return {
        canopyM2,
        carbonSequestration: canopyM2 * factor * BASE_RATES_PER_M2_PER_YEAR.carbonSequestration,
        stormwaterInterception: canopyM2 * factor * BASE_RATES_PER_M2_PER_YEAR.stormwaterInterception,
        energySavings: canopyM2 * factor * BASE_RATES_PER_M2_PER_YEAR.energySavings,
        airQualityImprovement: canopyM2 * factor * BASE_RATES_PER_M2_PER_YEAR.airQualityImprovement,
    };
}