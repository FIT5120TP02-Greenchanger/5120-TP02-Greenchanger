import {
    TREES_URL,
    PARCELS_URL,
    MIN_TREE_HEIGHT,
    MAPBOX_TOKEN,
    API_BASE_URL
} from "../config/mapConfig";
import { circleMetres, polygonAreaM2 } from "../utils/geo";

// bounds: { west, south, east, north }
export async function fetchTrees(bounds) {
    const params = new URLSearchParams({
        geometry: [bounds.west, bounds.south, bounds.east, bounds.north].join(","),
        geometryType: "esriGeometryEnvelope",
        inSR: "4326",
        outSR: "4326",
        spatialRel: "esriSpatialRelIntersects",
        where: "height_m >= " + MIN_TREE_HEIGHT,
        outFields: "canopy_radius_m,height_m",
        returnGeometry: "true",
        resultRecordCount: "2000",
        f: "geojson",
    });

    const res = await fetch(TREES_URL + "?" + params);
    const gj = await res.json();
    if (!gj || !gj.features) return { features: [], truncated: false };

    const features = gj.features.map((f) => {
        const [lng, lat] = f.geometry.coordinates;
        const r = f.properties.canopy_radius_m || 2;
        return {
            type: "Feature",
            properties: { r, area: Math.PI * r * r, lng, lat },
            geometry: circleMetres(lng, lat, r),
        };
    });
    return { features, truncated: gj.features.length >= 2000};
}

export async function fetchParcels(bounds) {
    const params = new URLSearchParams({
        geometry: [bounds.west, bounds.south, bounds.east, bounds.north].join(","),
        geometryType: "esriGeometryEnvelope",
        inSR: "4326",
        outSR: "4326",
        spatialRel: "esriSpatialRelIntersects",
        outFields: "prop_pfi,prop_propnum,prop_property_type",
        returnGeometry: "true",
        resultRecordCount: "2000",
        f: "geojson",
    });

    const gj = await (await fetch(PARCELS_URL + "?" + params)).json();
    if (!gj || !gj.features) return { features: [], truncated: false };

    const features = gj.features.map((f) => {
        f.properties.areaM2 = polygonAreaM2(f.geometry);
        return f;
    });
    return { features, truncated: gj.features.length >= 2000 };
}

export async function fetchParcelsAtPoint(lng, lat) {
    const params = new URLSearchParams({
        geometry: `${lng},${lat}`,
        geometryType: "esriGeometryPoint",
        inSR: "4326",
        outSR: "4326",
        spatialRel: "esriSpatialRelIntersects",
        outFields: "prop_pfi,prop_propnum,prop_property_type",
        returnGeometry: "true",
        f: "geojson",
    });
    const gj = await (await fetch(PARCELS_URL + "?" + params)).json();
    return gj.features || [];
}

// Normalizer address, temp fix
function toBaselineAddressFormat(mapboxLabel) {
    if (!mapboxLabel) return mapboxLabel;

    let s = mapboxLabel
        .replace(/,\s*Australia$/i, '')      // drop trailing country
        .replace(/\b(Victoria|VIC)\b/gi, '')          // drop state abbreviation, if present
        .replace(/,/g, ' ')                  // commas -> spaces
        .replace(/\s+/g, ' ')                // collapse multiple spaces
        .trim()
        .toUpperCase();

    return s;
}

export async function reverseGeocode(lng, lat) {
    const url =
        "https://api.mapbox.com/search/geocode/v6/reverse?" +
        new URLSearchParams({
        longitude: lng,
        latitude: lat,
        types: "address",
        access_token: MAPBOX_TOKEN,
        });
    try {
        const geo = await (await fetch(url)).json();
        const feature = geo.features?.[0];
        const raw = feature?.properties?.full_address || null;
        // return feature?.properties?.full_address || null;
        return raw ? toBaselineAddressFormat(raw) : null;
    } catch (err) {
        console.warn("reverse geocode failed", err);
        return null;
    }
}

export async function geocodeAddress(query) {
    const url =
        "https://api.mapbox.com/search/geocode/v6/forward?" +
        new URLSearchParams({ q: query, country: "AU", limit: "1", access_token: MAPBOX_TOKEN });
    const geo = await (await fetch(url)).json();
    if (!geo.features || !geo.features.length) return null;
    const [lng, lat] = geo.features[0].geometry.coordinates;
    const label = (geo.features[0].properties || {}).full_address || query;
    return { lng, lat, label };
}

export function resolveParcel(features, { clickPrecise, query = "", label } = {}) {
    if (!features.length) return null;
    const wantsUnit = /^\s*(unit|apt|apartment|flat)\b|\d\s*\//i.test(query);
    const smallestFirst = clickPrecise || wantsUnit;

    const withArea = features.map((f) => {
        f.properties.areaM2 = f.properties.areaM2 ?? polygonAreaM2(f.geometry);
        if (label) f.properties.ezi_address = label;
        return f;
    });

    withArea.sort((a, b) =>
        smallestFirst ? a.properties.areaM2 - b.properties.areaM2 : b.properties.areaM2 - a.properties.areaM2
    );
    return withArea[0];
}

export async function searchAddresses(query, limit = 10) {
    const params = new URLSearchParams({ q: query, limit: String(limit) });
    const res = await fetch(`${API_BASE_URL}/api/addresses?${params}`);
    if (!res.ok) return [];
    return res.json();
}

export async function fetchPropertyBaseline(address) {
    const params = new URLSearchParams({ address });
    const res = await fetch(`${API_BASE_URL}/api/properties/baseline?${params}`);
    if (!res.ok) return null;
    return res.json(); // shape TBD — inspect a real response before wiring up
}

export async function simulateScenario(actionType, inputs) {
    const res = await fetch(`${API_BASE_URL}/api/scenario/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action_type: actionType, inputs }),
    });
    if (!res.ok) return null;
    return res.json();
}

export async function fetchModelAssumptions() {
    const res = await fetch(`${API_BASE_URL}/api/meta/assumptions`);
    if (!res.ok) return null;
    return res.json();
}
