import { useState, useCallback, useMemo } from "react";
import { fetchTrees } from "../services/vicmap";
import { viewAreaM2 } from "../utils/geo";
import { MIN_TREE_ZOOM } from "../config/mapConfig";

export function useTreeCanopy() {
    const [treeFeatures, setTreeFeatures] = useState([]);
    const [truncated, setTruncated] = useState(false);
    const [loading, setLoading] = useState(false);
    const [lastBounds, setLastBounds] = useState(null);
    const [lastCenterLat, setLastCenterLat] = useState(null);

    const refresh = useCallback(async (mapboxBounds, centerLat, zoom) => {
        if (zoom != null && zoom < MIN_TREE_ZOOM) {
            setTreeFeatures([]);
            setTruncated(false);
            setLastBounds(null);
            setLastCenterLat(null);
            return;
        }
        setLoading(true);
        try {
        const bounds = {
            west: mapboxBounds.getWest(),
            south: mapboxBounds.getSouth(),
            east: mapboxBounds.getEast(),
            north: mapboxBounds.getNorth(),
        };
        const { features, truncated: wasTruncated } = await fetchTrees(bounds);
        setTreeFeatures(features);
        setTruncated(wasTruncated);
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

    return { treeFeatures, truncated, ...stats, loading, refresh };
}