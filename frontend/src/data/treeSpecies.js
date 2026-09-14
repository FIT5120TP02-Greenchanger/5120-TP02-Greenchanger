// Species catalogue for the planting flow. `benefitFactor` is a placeholder multiplier
// reflecting relative canopy density/type — swap for GreenShift's sourced per-species
// coefficients when available (see the TREE_SIZES radiusM note in hooks/simulation.js).
import water_gum from './images/species/Water-Gum.webp'
import lemon_scented_gum from './images/species/lemon_scented_gum.webp'
import crepe_myrtle from './images/species/crepe_myrtle.webp'
export const TREE_SPECIES = [
    {
        id: 'water_gum',
        commonName: 'Water Gum',
        scienceName: 'Tristaniopsis laurina',
        image: water_gum,
        price: {
            Small: 45,
            Medium: 90,
            Large: 160
        },
        benefitFactor: 1.15,
    },
    {
        id: 'lemon_scented gum',
        commonName: 'Lemon-scented Gum',
        scienceName: 'Corymbia citriodora',
        image: lemon_scented_gum,
        price: {
            Small: 55, 
            Medium: 105, 
            Large: 190
        },
        benefitFactor: 0.85,
    },
    {
        id: 'crepe_myrtle',
        commonName: 'Crepe Myrtle',
        image: crepe_myrtle,
        price: {
            Small: 60, 
            Medium: 115, 
            Large: 210
        },
        benefitFactor: 1.3,
    },
];