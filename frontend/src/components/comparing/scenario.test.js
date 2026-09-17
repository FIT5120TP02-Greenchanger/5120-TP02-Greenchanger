// scenarioMetrics.test.js
import { describe, it, expect } from 'vitest'
import { addedCanopyCentral, canopyCoverAfter, canopyDiffLabel } from './scenarioMetrics'

describe('addedCanopyCentral', () => {
    it('uses canopy_m2_median (the model p50) when present', () => {
        const row = { growth: { canopy_m2_median: 55, canopy_m2_min: 20, canopy_m2_max: 80 } }
        expect(addedCanopyCentral(row)).toBe(55)
    })

    it('demonstrates the p50 diverging from the min/max midpoint on an asymmetric distribution', () => {
        // p10=20, p50=55, p90=80 — independently fitted, so median != (min+max)/2 (=50)
        const row = { growth: { canopy_m2_median: 55, canopy_m2_min: 20, canopy_m2_max: 80 } }
        expect(addedCanopyCentral(row)).not.toBe((20 + 80) / 2)
    })

    it('falls back to the min/max midpoint when median is absent', () => {
        const row = { growth: { canopy_m2_min: 20, canopy_m2_max: 60 } }
        expect(addedCanopyCentral(row)).toBe(40)
    })

    it('returns null with no median and an incomplete min/max pair', () => {
        expect(addedCanopyCentral({ growth: { canopy_m2_min: 20 } })).toBeNull()
        expect(addedCanopyCentral({ growth: {} })).toBeNull()
        expect(addedCanopyCentral(null)).toBeNull()
    })
})

describe('canopyCoverAfter (uses addedCanopyCentral under the hood)', () => {
    it('computes before/after coverage off the p50 estimate, not the midpoint', () => {
        const row = { growth: { canopy_m2_median: 55, canopy_m2_min: 20, canopy_m2_max: 80 } }
        const result = canopyCoverAfter(row, 100, 1000)
        // after: (100 + 55) / 1000 = 15.5%, NOT (100 + 50) / 1000 = 15%
        expect(result.pct).toBeCloseTo(15.5, 5)
        expect(result.pct).not.toBeCloseTo(15, 5)
    })
})

describe('PreferredScenario canopyDiffLabel', () => {
    // canopyDiffLabel is currently a private, unexported function in PreferredScenario.jsx.
    // Exporting it (a one-line change: `export function canopyDiffLabel(...)`) is needed
    // for these to actually import and run it directly — see note below.

    it('compares two scenarios using their p50 estimates', () => {
        const preferred = { growth: { canopy_m2_median: 78 } }  // e.g. Lemon-scented Gum, Medium
        const other = { growth: { canopy_m2_median: 44 } }      // e.g. Water Gum, Small
        expect(canopyDiffLabel(preferred, other)).toBe('+34 m² more')
    })

    it('falls back to the midpoint per-side when a scenario has no median', () => {
        const preferred = { growth: { canopy_m2_median: 78 } }
        const other = { growth: { canopy_m2_min: 30, canopy_m2_max: 50 } } // midpoint 40
        expect(canopyDiffLabel(preferred, other)).toBe('+38 m² more')
    })

    it('reports Same when both central estimates are equal', () => {
        const preferred = { growth: { canopy_m2_median: 50 } }
        const other = { growth: { canopy_m2_median: 50 } }
        expect(canopyDiffLabel(preferred, other)).toBe('Same')
    })

    it('reports "less" when the preferred scenario has a smaller central estimate', () => {
        const preferred = { growth: { canopy_m2_median: 30 } }
        const other = { growth: { canopy_m2_median: 60 } }
        expect(canopyDiffLabel(preferred, other)).toBe('-30 m² less')
    })

    it('returns — when either scenario has no usable canopy data at all', () => {
        expect(canopyDiffLabel({ growth: {} }, { growth: { canopy_m2_median: 60 } })).toBe('—')
        expect(canopyDiffLabel({ growth: { canopy_m2_median: 60 } }, null)).toBe('—')
    })
})