export function buildChatbotTrees(simulatedTrees) {
    return (simulatedTrees ?? [])
        .filter((tree) => tree?.scenario)       // drop entries with no scenario
        .map((tree, index) => {
            const { species, size, growth, impact, costs, position } = tree.scenario
            return {
                tree_number: index + 1,          // numbered after filtering, so no gaps
                species: species?.common_name,
                scientific_name: species?.scientific_name,
                size,
                growth: growth ? {
                    canopy_m2_min: growth.canopy_m2_min,
                    canopy_m2_median: growth.canopy_m2_median,
                    canopy_m2_max: growth.canopy_m2_max,
                    height_m_min: growth.height_m_min,
                    height_m_median: growth.height_m_median,
                    height_m_max: growth.height_m_max,
                    crown_width_m_min: growth.crown_width_m_min,
                    crown_width_m_median: growth.crown_width_m_median,
                    crown_width_m_max: growth.crown_width_m_max,
                    timeframe_years: growth.equivalent_age_years,
                } : null,
                impact: impact ? {
                    impact_area_m2_min: impact.impact_area_range_m2?.minimum,
                    impact_area_m2_max: impact.impact_area_range_m2?.maximum,
                    temperature_change_c_min: impact.temperature_change_range_c?.minimum,
                    temperature_change_c_max: impact.temperature_change_range_c?.maximum,
                    projected_canopy_m2_min: impact.projected_canopy_range_m2?.minimum,
                    projected_canopy_m2_max: impact.projected_canopy_range_m2?.maximum,
                } : null,
                cost: costs ? {
                    min_aud: costs.minimum_cost,
                    max_aud: costs.maximum_cost,
                    currency: costs.currency,
                } : null,
                position,
            }
        })
}

export function buildChatbotSpeciesCatalogue(speciesCatalogue) {
    return (speciesCatalogue ?? []).map((s) => ({
        scientific_name: s.scientific_name,
        common_name: s.common_name,
        has_growth_model: s.has_growth_model,
    }))
}