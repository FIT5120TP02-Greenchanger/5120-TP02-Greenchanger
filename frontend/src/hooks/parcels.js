import { useState, useCallback } from "react";
import { fetchParcels } from "../services/vicmap";
import { MIN_PARCEL_ZOOM } from "../config/mapConfig";

// Replaces data.js's loadParcels(). Gated on the same zoom threshold —
// below it, a viewport can hold more than the 2000-record cap, so
// boundaries would be silently incomplete.
export function useParcels() {
    const [parcelFeatures, setParcelFeatures] = useState([]);
    const [truncated, setTruncated] = useState(false);
    const [hint, setHint] = useState("Click any property to select it.");
    const [loading, setLoading] = useState(false);

    const refresh = useCallback(async (mapboxBounds, zoom) => {
        if (zoom < MIN_PARCEL_ZOOM) {
        setParcelFeatures([]);
        setHint("Zoom in to load property boundaries.");
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
        const { features, truncated } = await fetchParcels(bounds);
        setParcelFeatures(features);
        setTruncated(truncated);
        setHint(
            truncated
            ? "Showing the first 2000 properties — zoom in for a complete picture."
            : "Click any property to select it."
        );
        } catch (err) {
        console.warn("Vicmap property query failed", err);
        } finally {
        setLoading(false);
        }
    }, []);

    return { parcelFeatures, truncated, hint, setHint, loading, refresh };
}
