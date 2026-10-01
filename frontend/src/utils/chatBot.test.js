import { describe, it, expect } from 'vitest'
import { buildChatbotTrees, buildChatbotSpeciesCatalogue } from './chatBot'

const fullScenario = {
    species: { common_name: 'White Cedar', scientific_name: 'Melia azedarach' },
    size: 'Medium',
    growth: { canopy_m2_min: 8.6, canopy_m2_median: 30, canopy_m2_max: 56.1, equivalent_age_years: 25 },
    impact: {
        impact_area_range_m2: { minimum: 10, maximum: 60 },
        temperature_change_range_c: { minimum: -0.5, maximum: -0.1 },
        projected_canopy_range_m2: { minimum: 8, maximum: 56 },
    },
    costs: { minimum_cost: 20, maximum_cost: 40, currency: 'AUD' },
    position: { lng: 145, lat: -37.9 },
}

describe('buildChatbotTrees', () => {
    it('maps a complete scenario', () => {
        const [tree] = buildChatbotTrees([{ scenario: fullScenario }])
        expect(tree).toMatchObject({
            tree_number: 1,
            species: 'White Cedar',
            scientific_name: 'Melia azedarach',
            size: 'Medium',
            cost: { min_aud: 20, max_aud: 40, currency: 'AUD' },
        })
        expect(tree.growth.timeframe_years).toBe(25)
        expect(tree.impact.temperature_change_c_min).toBe(-0.5)
    })

    it('returns [] for null or undefined input', () => {
        expect(buildChatbotTrees(null)).toEqual([])
        expect(buildChatbotTrees(undefined)).toEqual([])
    })

    it('skips trees with no scenario instead of throwing', () => {
        const result = buildChatbotTrees([{}, null, { scenario: fullScenario }])
        expect(result).toHaveLength(1)
        expect(result[0].tree_number).toBe(1) // numbered after filtering
    })

    it('sets growth, impact and cost to null when absent', () => {
        const [tree] = buildChatbotTrees([{ scenario: { species: { common_name: 'X' }, size: 'Small' } }])
        expect(tree.growth).toBeNull()
        expect(tree.impact).toBeNull()
        expect(tree.cost).toBeNull()
    })

    it('tolerates a partial impact object', () => {
        const [tree] = buildChatbotTrees([{ scenario: { ...fullScenario, impact: {} } }])
        expect(tree.impact.impact_area_m2_min).toBeUndefined()
    })

    it('tolerates a missing species', () => {
        const [tree] = buildChatbotTrees([{ scenario: { size: 'Small' } }])
        expect(tree.species).toBeUndefined()
    })
})

describe('buildChatbotSpeciesCatalogue', () => {
    it('keeps only the fields the chatbot needs', () => {
        const out = buildChatbotSpeciesCatalogue([
            { scientific_name: 'A', common_name: 'a', has_growth_model: true, image_url: 'x' },
        ])
        expect(out).toEqual([{ scientific_name: 'A', common_name: 'a', has_growth_model: true }])
    })

    it('handles null', () => {
        expect(buildChatbotSpeciesCatalogue(null)).toEqual([])
    })
})