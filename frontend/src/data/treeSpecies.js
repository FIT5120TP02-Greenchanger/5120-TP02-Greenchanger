// Species catalogue for the planting flow. `benefitFactor` is a placeholder multiplier
// reflecting relative canopy density/type — swap for GreenShift's sourced per-species
// coefficients when available (see the TREE_SIZES radiusM note in hooks/simulation.js).
import eucalyptus from './images/species/eucalyptus.jpg'
import acacia from './images/species/acacia.jpg'
import melaleuca from './images/species/melaleuca.webp'
import london_plane from './images/species/plane-tree.jpg'
export const TREE_SPECIES = [
    {
        id: 'eucalyptus',
        commonName: 'Eucalyptus',
        image: eucalyptus,
        description: 'Fast-growing native with a broad, dense canopy — strong shading and stormwater benefits.',
        benefitFactor: 1.15,
    },
    {
        id: 'acacia',
        commonName: 'Acacia (Wattle)',
        image: acacia,
        description: 'Compact native suited to smaller lots, with a lighter canopy.',
        benefitFactor: 0.85,
    },
    {
        id: 'plane-tree',
        commonName: 'London Plane',
        image: london_plane,
        description: 'Large deciduous shade tree common in Melbourne streetscapes.',
        benefitFactor: 1.3,
    },
    {
        id: 'melaleuca',
        commonName: 'Melaleuca (Paperbark)',
        image: melaleuca,
        description: 'Hardy native tolerant of wet or compacted soils, moderate canopy.',
        benefitFactor: 1.0,
    },
];