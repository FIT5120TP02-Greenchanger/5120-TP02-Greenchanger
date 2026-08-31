/* ============================================================
   Pure geometry helpers — no fetch, no React, no DOM, no global `map`.
   Every function takes what it needs as an argument.
   ============================================================ */

// A circle of radius r metres around [lng,lat], as a GeoJSON polygon
export function circleMetres(lng, lat, r, steps = 24) {
    const dLat = r / 110574;
    const dLng = r / (111320 * Math.cos((lat * Math.PI) / 180));
    const ring = [];
    for (let i = 0; i <= steps; i++) {
        const t = (i / steps) * 2 * Math.PI;
        ring.push([lng + dLng * Math.cos(t), lat + dLat * Math.sin(t)]);
    }
    return { type: "Polygon", coordinates: [ring] };
}

export const fmtArea = (m2) =>
    m2 > 10000 ? (m2 / 10000).toFixed(2) + " ha" : Math.round(m2) + " m\u00b2";

export function ringAreaM2(ring) {
    if (ring.length < 4) return 0;
    let lat0 = 0;
    for (const p of ring) lat0 += p[1];
    lat0 /= ring.length;
    const kx = 111320 * Math.cos((lat0 * Math.PI) / 180);
    const ky = 110574;
    let s = 0;
    for (let i = 0; i < ring.length - 1; i++) {
        s +=
        ring[i][0] * kx * (ring[i + 1][1] * ky) -
        ring[i + 1][0] * kx * (ring[i][1] * ky);
    }
    return Math.abs(s) / 2;
}

export function polygonAreaM2(geom) {
    const polys = geom.type === "MultiPolygon" ? geom.coordinates : [geom.coordinates];
    let a = 0;
    for (const rings of polys) {
        a += ringAreaM2(rings[0]);
        for (let i = 1; i < rings.length; i++) a -= ringAreaM2(rings[i]); // subtract holes
    }
    return a;
}

// ray casting — is this tree standing on this property?
export function pointInRing(lng, lat, ring) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
        if ((yi > lat) !== (yj > lat) && lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) {
        inside = !inside;
        }
    }
    return inside;
}

export function pointInPolygon(lng, lat, geom) {
    const polys = geom.type === "MultiPolygon" ? geom.coordinates : [geom.coordinates];
    for (const rings of polys) {
        if (!pointInRing(lng, lat, rings[0])) continue;
        let inHole = false;
        for (let i = 1; i < rings.length; i++) if (pointInRing(lng, lat, rings[i])) inHole = true;
        if (!inHole) return true;
    }
    return false;
}

// Was `viewAreaM2()` reading a global `map` in the vanilla version.
// Now it takes bounds + centerLat as arguments — the caller (a hook)
// is the one that has access to the map instance, not this file.
export function viewAreaM2(bounds, centerLat) {
  const w = (bounds.east - bounds.west) * 111320 * Math.cos((centerLat * Math.PI) / 180);
  const h = (bounds.north - bounds.south) * 110574;
  return Math.abs(w * h);
}