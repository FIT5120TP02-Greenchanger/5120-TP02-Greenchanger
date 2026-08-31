import { useState, useMemo, useCallback } from "react";
import { polygonAreaM2, pointInPolygon, circleMetres, fmtArea } from "../utils/geo";
import { fetchParcelsAtPoint, resolveParcel, geocodeAddress, reverseGeocode, fetchPropertyBaseline } from "../services/vicmap";

// Replaces property.js's `let selected` + selectFeature()/selectAtPoint()/
// findAddress(). Same logic, but derived stats come back as data (via
// useMemo) instead of textContent writes.

const RADIUS_M = 50;

export function useSelectedProperty(treeFeatures) {
    const [selected, setSelected] = useState(null);
    const [selectedLabel, setSelectedLabel] = useState(null);
    const [hint, setHint] = useState(null);

    const clearSelection = useCallback(() => {
        setSelected(null);
        setSelectedLabel(null);
    }, []);

    const selectFeature = useCallback((feature, label) => {
        setSelected(feature);
        setSelectedLabel(label || null);
        setHint(null);
    }, []);

    const selectAtPoint = useCallback(async (hits, parcelFeatures, zoomTooLow, lngLat) => {
        if (!hits.length) {
            if (zoomTooLow) {
                clearSelection();
                setHint("Zoom in to load property boundaries.");
                return;
            }
            if (!lngLat) {
                clearSelection();
                setHint("Nothing here — roads and reserves have no property polygon.");
                return;
            }
            const circleGeom = circleMetres(lngLat.lng, lngLat.lat, RADIUS_M);
            selectFeature(
                { type: "Feature", properties: { kind: "circle" }, geometry: circleGeom },
                `${RADIUS_M}m around your click`
            );
            return;
        }

        const ids = hits.map((h) => h.properties.prop_pfi);
        let full = parcelFeatures.filter((p) => ids.indexOf(p.properties.prop_pfi) >= 0);
        if (lngLat && full.length > 1) {
        const containing = full.filter((p) => pointInPolygon(lngLat.lng, lngLat.lat, p.geometry));
        if (containing.length) full = containing;
        }
        const pool = full.length ? full : hits;
        const best = resolveParcel(pool, { clickPrecise: true });
        selectFeature(best);
        if (lngLat) {
        const label = await reverseGeocode(lngLat.lng, lngLat.lat);
        if (label) selectFeature(best, label);
        }
    }, [clearSelection, selectFeature]);

    

    const resolveFromCoordinates = useCallback(async (lng, lat, { query = "", label } = {}) => {
        const feats = await fetchParcelsAtPoint(lng, lat);
        if (!feats.length) {
            clearSelection();
            setHint((label || query) + " geocoded onto a road or reserve. Click the house itself.");
            return null;
        }
        const best = resolveParcel(feats, { clickPrecise: false, query, label });
        selectFeature(best, label);
        return { lng, lat, feature: best };
    }, [clearSelection, selectFeature]);

    const selectByAddress = useCallback(async (query) => {
        setHint(`Looking up ${query} …`);
        const geo = await geocodeAddress(query);
        if (!geo) {
            setHint("Mapbox could not find that address.");
            return null;
        }
        return resolveFromCoordinates(geo.lng, geo.lat, { query, label: geo.label });
    }, [resolveFromCoordinates]);

    const resolveFromBaseline = useCallback(async (address) => {
        setHint(`Looking up ${address} …`);
        const baseline = await fetchPropertyBaseline(address);
        if (!baseline) {
            clearSelection();
            setHint("Could not find a property baseline for that address.");
            return null;
        }
        const feature = {
            type: "Feature",
            properties: {
            areaM2: baseline.lot_area_m2,
            mappedTreeCount: baseline.mapped_tree_count,
            neighbourhoodCanopyPct: baseline.neighbourhood_canopy_percentage,
            canopyClassification: baseline.canopy_classification,
            landSurfaceTempC: baseline.land_surface_temperature,
            },
            geometry: baseline.geometry, // assumed to come back as GeoJSON
        };
        selectFeature(feature, address);
        return { feature, baseline };
        },
        [clearSelection, selectFeature]
    );

    const stats = useMemo(() => {
        if (!selected) return null;
        const lotArea = selected.properties.areaM2 || polygonAreaM2(selected.geometry);
        const onLot = treeFeatures.filter((t) =>
            pointInPolygon(t.properties.lng, t.properties.lat, selected.geometry)
        );
        const canopy = onLot.reduce((a, t) => a + t.properties.area, 0);
        return {
            address: selectedLabel || selected.properties.ezi_address || `PFI ${selected.properties.prop_pfi}`,
            areaLabel: fmtArea(lotArea),
            treeCount: onLot.length,
            canopyPct: lotArea ? ((canopy / lotArea) * 100).toFixed(1) + "%" : "—",
            isCircle: selected.properties?.kind === "circle",
            // Only present when selectFeature came from resolveFromBaseline —
            // undefined otherwise, so PropertyPanel can conditionally show these.
            landSurfaceTempC: selected.properties?.landSurfaceTempC,
            neighbourhoodCanopyPct: selected.properties?.neighbourhoodCanopyPct,
            canopyClassification: selected.properties?.canopyClassification,
        };
    }, [selected, selectedLabel, treeFeatures]);

    return {
        selected,
        stats,
        hint,
        setHint,
        selectFeature,
        selectAtPoint,
        selectByAddress,
        resolveFromCoordinates,
        resolveFromBaseline,
        clearSelection,
    };
}
