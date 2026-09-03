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
    const [trees, setTrees] = useState([]);
    const [size, setSize] = useState("Medium");
    
    const startPlanting = useCallback(() => setActive(true), []);
    const cancelPlanting = useCallback(() => setActive(false), []);
    
    const placeTree = useCallback((lng, lat) => {
        setTrees((prev) => [...prev, { lng, lat, radiusM: TREE_SIZES[size].radiusM, size }]);
        setActive(false);
    }, [size]);
    
    const removeAllTree = useCallback(() => {
        setTrees([]);
        setActive(true);
    }, []);
    
    const removeTreeAt = useCallback((index) => {
        setTrees((prev) => prev.filter((_, i) => i !== index));
        if (trees.length === 1) setActive(true);
    }, [trees.length]);
    
    return {
        active,
        trees,
        size,
        setSize,
        startPlanting,
        cancelPlanting,
        placeTree,
        removeAllTree,
        removeTreeAt,
    };
}