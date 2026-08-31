import { useState, useCallback, useMemo } from "react";
import { fetchTrees } from "../services/vicmap";
import { viewAreaM2 } from "../utils/geo";

export function useTreeCanopy() {
    const [treeFeatures, setTreeFeatures] = useState([]);
    const [loading, setLoading] = useState(false);
    const [lastBounds, setLastBounds] = useState(null);
    const [lastCenterLat, setLastCenterLat] = useState(null);

    const refresh = useCallback(async (mapboxBounds, centerLat) => {
        setLoading(true);
        try {
        const bounds = {
            west: mapboxBounds.getWest(),
            south: mapboxBounds.getSouth(),
            east: mapboxBounds.getEast(),
            north: mapboxBounds.getNorth(),
        };
        const features = await fetchTrees(bounds);
        setTreeFeatures(features);
        setLastBounds(bounds);
        setLastCenterLat(centerLat);
        } catch (err) {
        console.warn("Vicmap tree query failed", err);
        } finally {
        setLoading(false);
        }
    }, []);

    const stats = useMemo(() => {
        if (!lastBounds || lastCenterLat == null) {
        return { nTrees: 0, canopyM2: 0, viewM2: 0, pct: 0 };
        }
        const area = viewAreaM2(lastBounds, lastCenterLat);
        const canopy = treeFeatures.reduce((a, f) => a + f.properties.area, 0);
        return {
        nTrees: treeFeatures.length,
        canopyM2: canopy,
        viewM2: area,
        pct: area ? (canopy / area) * 100 : 0,
        };
    }, [treeFeatures, lastBounds, lastCenterLat]);

    return { treeFeatures, ...stats, loading, refresh };
}