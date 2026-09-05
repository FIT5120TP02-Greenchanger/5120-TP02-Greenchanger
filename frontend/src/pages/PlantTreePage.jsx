// import { useRef, useCallback, useEffect, useMemo } from 'react';
import { useRef, useCallback, useEffect, useMemo, useState } from 'react'; // useState added (2026-09-03): tree position + hint
import Map, { Source, Layer } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import styles from './PlantTreePage.module.css';
// import panelStyles from '../components/Panel.module.css'; // only used by the screen-centre crosshair, replaced 2026-09-03
import { useTreeSimulation } from '../hooks/simulation';
import TreePlacementPanel from '../components/TreePlacementPanel';
import ComparisonPanel from '../components/ComparisonPanel'
// import { circleMetres } from '../utils/geo';
import { circleMetres, centroidOfGeometry, pointInPolygon } from '../utils/geo'; // lot centre + inside-lot check (2026-09-03)
import { TREE_SIZES } from '../hooks/simulation'; // canopy radius per size for the preview circle (2026-09-03)
import { useTreeCanopy } from '../hooks/canopy';
import { START_PITCH, START_BEARING } from '../config/mapConfig';

// Planting map (2026-09-03): same paint as MapView so the existing canopy and the selected lot
// look like the map the user came from.
const canopyLayer = {
    id: "canopy",
    type: "fill-extrusion",
    paint: {
        "fill-extrusion-color": "#7FA96C",
        "fill-extrusion-height": ["*", ["get", "r"], 1.6],
        "fill-extrusion-base": ["*", ["get", "r"], 0.9],
        "fill-extrusion-opacity": 0.85,
    },
};
const lotFillLayer = { id: "lot-fill", type: "fill", paint: { "fill-color": "#2F7D5A", "fill-opacity": 0.2 } };
const lotLineLayer = { id: "lot-line", type: "line", paint: { "line-color": "#2F7D5A", "line-width": 3 } };
const EMPTY = { type: 'FeatureCollection', features: [] };

export default function PlantTreePage({ planTarget, onDone }) {
    const mapRef = useRef(null);
    const debounceRef = useRef(null);

    const simulation = useTreeSimulation();
    const trees = useTreeCanopy();

    // Placement (2026-09-03): the user plants the tree themselves. The dashed preview circle
    // (a real ground circle sized by the chosen tree, so it follows the map perspective) follows
    // the cursor until the first click, then sits where the user clicked; further clicks move it.
    // Planting outside the selected lot is allowed and only triggers a short hint.
    const lotGeometry = planTarget?.feature?.geometry || null;
    const lotCentre = useMemo(
        () => centroidOfGeometry(lotGeometry) || { lng: planTarget?.lng ?? 145.13, lat: planTarget?.lat ?? -37.918 },
        [lotGeometry, planTarget?.lng, planTarget?.lat]
    );
    const [treePos, setTreePos] = useState(null);   // where the user clicked
    const [hoverPos, setHoverPos] = useState(null); // cursor position before the first click
    const [hint, setHint] = useState(null);

    const refreshTrees = useCallback(() => {
        const map = mapRef.current?.getMap();
        if (!map) return;
        trees.refresh(map.getBounds(), map.getCenter().lat, map.getZoom());
    }, [trees]);


    useEffect(() => {
        simulation.startPlanting();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const handleMapLoad = useCallback(() => refreshTrees(), [refreshTrees]);
    const handleMoveEnd = useCallback(() => {
        clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(refreshTrees, 250);
    }, [refreshTrees]);

    // const handleConfirm = useCallback(() => {
    //     const center = mapRef.current?.getMap()?.getCenter();
    //     if (center) simulation.placeTree(center.lng, center.lat);
    // }, [simulation]);
    // Plant where the user put the preview circle (2026-09-03)
    const handleConfirm = useCallback(() => {
        if (!treePos) return;
        if(simulation.selectedId) {
            simulation.updateTree(simulation.selectedId, { lng: treePos.lng, lat: treePos.lat, size: simulation.size, radiusM: TREE_SIZES[simulation.size].radiusM });
        } else {
            simulation.placeTree(treePos.lng, treePos.lat, { id: crypto.randomUUID(), label: simulation.trees.length + 1 });
        }
    }, [simulation, treePos]);

    // Click = put the tree there. Outside the selected lot is allowed, just say so.
    const handleMapClick = useCallback((e) => {
        if (map?.getLayer('simulated-tree-fill')) {
            const map = mapRef.current?.getMap();
            const hitbox = map?.queryRenderedFeatures(e.point, { layers: ['simulated-tree-fill'] });
            if (hitbox?.length) {
                simulation.selectTree(hitbox[0].properties.id);
                return;
            }
        }
        if (!simulation.active) return;
        const { lng, lat } = e.lngLat;
        setTreePos({ lng, lat });
        if (lotGeometry && !pointInPolygon(lng, lat, lotGeometry)) {
            setHint("You are planting on another property.");
        }
    }, [simulation.active, lotGeometry]);

    // Before the first click the circle follows the cursor so the size is visible right away
    const handleMapMouseMove = useCallback((e) => {
        if (simulation.active && !treePos) setHoverPos({ lng: e.lngLat.lng, lat: e.lngLat.lat });
    }, [simulation.active, treePos]);
    const handleMapMouseLeave = useCallback(() => setHoverPos(null), []);

    useEffect(() => {
        if (!hint) return;
        const t = setTimeout(() => setHint(null), 3000);
        return () => clearTimeout(t);
    }, [hint]);

    // Dashed preview circle = canopy at maturity for the selected size, at the tree position
    const previewGeoJson = useMemo(() => {
        const pos = treePos || hoverPos;
        return {
            type: 'FeatureCollection',
            features: simulation.active && pos
                ? [{ type: 'Feature', properties: {}, geometry: circleMetres(pos.lng, pos.lat, TREE_SIZES[simulation.size].radiusM) }]
                : [],
        };
    }, [simulation.active, simulation.size, treePos, hoverPos]);

    const handleDiscard = useCallback(() => onDone(null), [onDone]);

    const handleFinish = useCallback(() => {
        onDone(simulation.trees.length ? simulation.trees : null);
    }, [simulation.trees, onDone]);

    const projected = useMemo(() => {
        if (!simulation.trees.length || !trees.viewM2) return null;
        const addedM2 = simulation.trees.reduce((sum, t) => sum + Math.PI * t.radiusM ** 2, 0);
        const pct = ((trees.canopyM2 + addedM2) / trees.viewM2) * 100;
        return { pct, deltaPts: pct - trees.pct };
    }, [simulation.trees, trees.canopyM2, trees.viewM2, trees.pct]);

    const simulatedTreesGeoJson = useMemo(() => ({
        type: 'FeatureCollection',
        features: simulation.trees.map((t) => ({
            type: 'Feature',
            properties: { id: t.id, label: t.label },
            geometry: circleMetres(t.lng, t.lat, t.radiusM),
        })),
    }), [simulation.trees])

    const handleRemoveTree = useCallback((id) => {
        const idx = simulation.trees.findIndex((t) => t.id === id);
        if (idx >= 0) simulation.removeTreeAt(idx);
    }, [simulation.trees, simulation.removeTreeAt]);

    const handleFocusTree = useCallback((tree) => {
        const map = mapRef.current?.getMap();
        if (!map) return;
        map.flyTo({ center: [tree.lng, tree.lat], zoom: Math.max(map.getZoom(), 19), speed: 1.2 });
        simulation.selectTree(tree.id);
    }, [simulation]);

    return (
        <div className={styles['plant-page']}>
            <header className={styles['plant-header']}>
                <div className={styles['brand']}>
                <span className={styles['brand-dot']} />
                <span>GreenChanger</span>
                </div>
                <button className={styles['close-button']} onClick={handleDiscard} aria-label="Discard">x</button>
            </header>

            <div className={styles['plant-body']}>
                <div className={styles['map-area']}>
                <Map
                    ref={mapRef}
                    onLoad={handleMapLoad}
                    onMoveEnd={handleMoveEnd}
                    onClick={handleMapClick}
                    onMouseMove={handleMapMouseMove}
                    onMouseLeave={handleMapMouseLeave}
                    cursor={simulation.active ? 'crosshair' : 'grab'}
                    mapboxAccessToken={import.meta.env.VITE_MAPBOX_ACCESS_TOKEN}
                    initialViewState={{
                    // longitude: planTarget?.lng ?? 145.13,
                    // latitude: planTarget?.lat ?? -37.918,
                    longitude: lotCentre.lng, // centre on the lot (2026-09-03)
                    latitude: lotCentre.lat,
                    zoom: 18.2,
                    pitch: START_PITCH,
                    bearing: START_BEARING,
                    }}
                    config={{ basemap: { lightPreset: 'day' } }}
                    style={{ width: '100%', height: '100%' }}
                    mapStyle="mapbox://styles/mapbox/standard"
                >
                    {/* Existing canopy + the selected lot (2026-09-03), so the simulated tree has context */}
                    <Source id="trees" type="geojson" data={{ type: 'FeatureCollection', features: trees.treeFeatures }}>
                        <Layer {...canopyLayer} source="trees" />
                    </Source>
                    <Source id="lot" type="geojson" data={lotGeometry ? { type: 'Feature', properties: {}, geometry: lotGeometry } : EMPTY}>
                        <Layer {...lotFillLayer} source="lot" />
                        <Layer {...lotLineLayer} source="lot" />
                    </Source>
                    {/* Preview circle while placing; the placed tree is drawn by the block below */}
                    <Source id="tree-preview" type="geojson" data={previewGeoJson}>
                        <Layer id="tree-preview-fill" type="fill" source="tree-preview" paint={{ 'fill-color': '#2F7D5A', 'fill-opacity': 0.2 }} />
                        <Layer id="tree-preview-line" type="line" source="tree-preview" paint={{ 'line-color': '#2F7D5A', 'line-width': 2, 'line-dasharray': [2, 2] }} />
                    </Source>

                    {simulation.trees.length && (
                    <Source
                        id="simulated-trees"
                        type="geojson"
                        data={simulatedTreesGeoJson}
                    >
                        <Layer id="simulated-tree-fill" type="fill" source="simulated-tree"
                            paint={{ 'fill-color': '#2F7D5A', 'fill-opacity': 0.35 }} />
                        <Layer id="simulated-tree-line" type="line" source="simulated-tree"
                            paint={{ 'line-color': '#2F7D5A', 'line-width': 2, 'line-dasharray': [2, 2] }} />
                        <Layer id="simulated-tree-label" type="symbol" source="simulated-tree"
                            layout={{ 'text-field': ['get', 'label'], 'text-size': 14 }}
                            paint={{ 'text-color': '#ffffff' }} />
                    </Source>
                    )}
                </Map>

                {/* Original kept for reference (2026-09-03):
                {simulation.active && (
                    <div className={styles['crosshair-overlay']}>
                    <div className={panelStyles['crosshair']} />
                    </div>
                )}
                */}

                <div className={styles['pilot-badge']}>Simulation is indicative, not professional advice</div>
                {/* Hint when the tree is put outside the selected lot (2026-09-03) */}
                {hint && <div className={styles['map-hint']} role="status">{hint}</div>}
                </div>

                <aside className={styles['plant-sidebar']}>
                    {simulation.trees.length > 0 && projected && !simulation.active ? (
                        <ComparisonPanel
                            baseline={{ pct: trees.pct }}
                            projected={projected}
                            trees={simulation.trees}
                            onAdd={simulation.startPlanting}
                            onReset={simulation.removeAllTree}
                            onRemoveTree={handleRemoveTree}
                            onFocusTree={handleFocusTree}
                            onFinish={handleFinish}
                        />
                    ) : (
                        <TreePlacementPanel
                            size={simulation.size}
                            onSizeChange={simulation.setSize}
                            onConfirm={handleConfirm}
                            onCancel={handleDiscard}
                            hasPosition={simulation.trees.length > 0}
                            canPlant={!!treePos}
                        />
                    )}
                </aside>
            </div>
        </div>
    );
}