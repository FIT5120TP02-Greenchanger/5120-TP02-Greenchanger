// Small pure helpers so TreeCompare and PreferredScenario compute the same
// numbers the same way. ASSUMPTION markers below are field names guessed
// from the screenshots — confirm against the real growth/costs shape.

const LEVEL_RANK = { Low: 0, Medium: 1, High: 2 }

export function canopyAddedRange(row) {
    if (!row?.growth) return null
    const { canopy_m2_min, canopy_m2_max } = row.growth
    if (canopy_m2_min == null || canopy_m2_max == null) return null
    return { min: canopy_m2_min, max: canopy_m2_max }
}

export function addedCanopyCentral(row) {
    if (!row?.growth) return
    const { canopy_m2_min, canopy_m2_median, canopy_m2_max } = row.growth
    if (canopy_m2_median != null) return canopy_m2_median
    if (canopy_m2_median != null && canopy_m2_max != null) return (canopy_m2_min + canopy_m2_max) / 2
    return null
}

// Canopy cover for the *whole current view*, before vs after adding this one tree.
// Mirrors the calc MapView already does for `projected` (see MapView.jsx).
export function canopyCoverAfter(row, canopyM2, viewM2) {
    const addedCentral = addedCanopyCentral(row)
    if(addedCentral == null || !view2) return null
    const basePct = (canopyM2 / viewM2) * 100
    const afterPct = ((canopyM2 + addedCentral) / viewM2) * 100
    return { pct: afterPct, deltaPts: afterPct - basePct }
}

// ASSUMPTION: crown width fields named like this — MapView.jsx already
// expects `crown_width_m_median` on growth, so matching min/max here.
export function matureCanopyWidthRange(row) {
    if (!row?.growth) return null
    const { crown_width_m_min, crown_width_m_max } = row.growth
    if (crown_width_m_min == null || crown_width_m_max == null) return null
    return { min: crown_width_m_min, max: crown_width_m_max }
}

// ASSUMPTION: no explicit "space needed" field seen anywhere yet — using the
// upper end of projected canopy area as a stand-in until there's a real one.
export function spaceNeededM2(row) {
    const added = canopyAddedRange(row)
    return added ? added.max : null
}

// ASSUMPTION: qualitative level fields on growth — rename if the API differs.
export function shadeLevel(row) { return row?.growth?.shade_potential ?? null }
export function coolingLevel(row) { return row?.growth?.cooling_potential ?? null }

export function priceRange(row) {
    if (!row?.costs) return null
    const { minimum_cost, maximum_cost } = row.costs
    if (minimum_cost == null) return null
    return minimum_cost === maximum_cost
        ? { min: minimum_cost, max: minimum_cost }
        : { min: minimum_cost, max: maximum_cost }
}

export function formatRange(range, unit = '') {
    if (!range) return '—'
    return range.min === range.max
        ? `${range.min}${unit}`
        : `${range.min}–${range.max}${unit}`
}

export function formatPrice(range) {
    if (!range) return '—'
    return range.min === range.max ? `$${range.min}` : `$${range.min}-$${range.max}`
}

// "One level higher" / "One level lower" / "Same" style diff for shade/cooling.
export function levelDiffLabel(a, b) {
    if (!a || !b) return '—'
    const diff = LEVEL_RANK[a] - LEVEL_RANK[b]
    if (diff === 0) return 'Same'
    const steps = Math.abs(diff)
    return `${steps} level${steps > 1 ? 's' : ''} ${diff > 0 ? 'higher' : 'lower'}`
}