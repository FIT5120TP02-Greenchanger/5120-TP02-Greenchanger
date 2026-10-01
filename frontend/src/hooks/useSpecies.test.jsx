import { renderHook, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fetchSpecies } from '../services/trees'
import { useSpecies, LOAD_ERROR } from './useSpecies'

vi.mock('../services/trees', () => ({ fetchSpecies: vi.fn() }))

const withModel = { species_key: 'a', common_name: 'A', has_growth_model: true }
const withoutModel = { species_key: 'b', common_name: 'B', has_growth_model: false }

describe('useSpecies', () => {
    beforeEach(() => {
        vi.clearAllMocks()
        vi.spyOn(console, 'error').mockImplementation(() => {})
    })

    it('loads species and filters out those without a growth model', async () => {
        fetchSpecies.mockResolvedValue({ species: [withModel, withoutModel] })
        const setCatalogue = vi.fn()
        const { result } = renderHook(() => useSpecies('1 Main St', setCatalogue))
        await waitFor(() => expect(setCatalogue).toHaveBeenCalledWith([withModel]))
        expect(result.current).toBeNull()
    })

    it('clears the error when a later request succeeds', async () => {
        fetchSpecies
            .mockRejectedValueOnce(new Error('network'))
            .mockResolvedValueOnce({ species: [withModel] })
        const setCatalogue = vi.fn()

        const { result, rerender } = renderHook(
            ({ address }) => useSpecies(address, setCatalogue),
            { initialProps: { address: 'A St' } },
        )
        await waitFor(() => expect(result.current).toBe(LOAD_ERROR))
        expect(setCatalogue).toHaveBeenLastCalledWith([])

        rerender({ address: 'B St' })
        await waitFor(() => expect(result.current).toBeNull())
        expect(setCatalogue).toHaveBeenLastCalledWith([withModel])
    })

    it('resets catalogue and error when the address is cleared', async () => {
        fetchSpecies.mockRejectedValueOnce(new Error('network'))
        const setCatalogue = vi.fn()
        const { result, rerender } = renderHook(
            ({ address }) => useSpecies(address, setCatalogue),
            { initialProps: { address: 'A St' } },
        )
        await waitFor(() => expect(result.current).toBe(LOAD_ERROR))
        rerender({ address: '' })
        await waitFor(() => expect(result.current).toBeNull())
        expect(setCatalogue).toHaveBeenLastCalledWith([])
    })
})