import { useState, useMemo, useCallback } from "react";
// import { polygonAreaM2, pointInPolygon, circleMetres, fmtArea } from "../utils/geo";
import { polygonAreaM2, pointInPolygon, fmtArea } from "../utils/geo"; // circleMetres unused since the circle fallback went (2026-09-03)
import { fetchParcelsAtPoint, resolveParcel, geocodeAddress, reverseGeocode, fetchPropertyBaseline } from "../services/vicmap";


// const RADIUS_M = 50; // only used by the removed 50 m circle fallback (2026-09-03)

function mapBaselineToProperties(baseline) {
return {
    areaM2: baseline.parcel_area_m2,
    mappedTreeCount: baseline.mapped_property_tree_count,
    neighbourhoodCanopyPct: baseline.neighbourhood_canopy_percentage,
    canopyClassification: baseline.canopy_classification,
    landSurfaceTempC: baseline.land_surface_temperature_c,
    landSurfaceTempDate: baseline.surface_temperature_observed_on,
    weatherStationName: baseline.weather_station_name,
    weatherObservedAt: baseline.weather_observed_at,
    weatherDistanceKm: baseline.weather_station_distance_km,
    // Expected values per README: "good_local_context" (<10km),
    // "regional_context_warning" (10-25km), or
    // "unavailable_no_observation_within_3_hours" (no eligible reading).
    // Beyond 25km, air/apparent temp should be suppressed server-side.
    weatherContext: baseline.air_temperature_context_status,
    airTemperatureC: baseline.current_air_temperature_c,
};
}

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
            // const circleGeom = circleMetres(lngLat.lng, lngLat.lat, RADIUS_M);
            // selectFeature(
                // { type: "Feature", properties: { kind: "circle" }, geometry: circleGeom },
                // `${RADIUS_M}m around your click`
            // );
            // return;
            // Arrive flow (2026-09-03): no 50 m circle fallback any more. A click that hits no
            // lot keeps the current selection and only shows a hint.
            setHint("Roads and reserves have no lot. Click a house.");
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
        if (!lngLat) return;
        const label = await reverseGeocode(lngLat.lng, lngLat.lat);
        if (!label) return;
        const baseline = await fetchPropertyBaseline(label);
        if (baseline) {
            const enriched = { ...best, properties: { ...best.properties, ...mapBaselineToProperties(baseline) } };
            selectFeature(enriched, label);
        } else {
            selectFeature(best, label);
        }

        },
        [clearSelection, selectFeature]
    );


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
            properties: mapBaselineToProperties(baseline),
            geometry: baseline.parcel_geometry_geojson
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
            landSurfaceTempC: selected.properties?.landSurfaceTempC,
            landSurfaceTempDate: selected.properties?.landSurfaceTempDate,
            neighbourhoodCanopyPct: selected.properties?.neighbourhoodCanopyPct,
            canopyClassification: selected.properties?.canopyClassification,
            weatherStationName: selected.properties?.weatherStationName,
            weatherObservedAt: selected.properties?.weatherObservedAt,
            weatherDistanceKm: selected.properties?.weatherDistanceKm,
            weatherContext: selected.properties?.weatherContext,
            airTemperatureC: selected.properties?.airTemperatureC,
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
