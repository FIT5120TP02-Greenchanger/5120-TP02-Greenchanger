import { useState, useCallback } from "react";
 
// Approximate mature canopy radius per size tier — tune against the data
// team's real Torquato et al. crown-area figures once you swap the
// TreeSimulator's placeholder prices for their sourced numbers.
export const TREE_SIZES = {
    Small: { radiusM: 1.5, heightLabel: "5m", price: "$100" },
    Medium: { radiusM: 3, heightLabel: "8m", price: "$500" },
    Large: { radiusM: 5, heightLabel: "12m", price: "$1000" },
    };
 
export function useTreeSimulation() {
    const [active, setActive] = useState(false);
    const [position, setPosition] = useState(null);
    const [size, setSize] = useState("Medium");
    
    const startPlanting = useCallback(() => setActive(true), []);
    const cancelPlanting = useCallback(() => setActive(false), []);
    
    const placeTree = useCallback((lng, lat) => {
        setPosition({ lng, lat });
        setActive(false);
    }, []);
    
    const removeTree = useCallback(() => {
        setPosition(null);
        setActive(true);
    }, []);
    
    const repositionTree = useCallback(() => setActive(true), []);
    
    return {
        active,
        position,
        size,
        setSize,
        radiusM: TREE_SIZES[size].radiusM,
        startPlanting,
        cancelPlanting,
        placeTree,
        removeTree,
        repositionTree,
    };
}