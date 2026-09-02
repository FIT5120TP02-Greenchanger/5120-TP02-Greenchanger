import { useRef, useCallback, useEffect, useMemo } from 'react';
import Map, { Source, Layer } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import styles from './PlantTreePage.module.css';
import panelStyles from '../components/Panel.module.css';
import { useTreeSimulation } from '../hooks/simulation';
import TreePlacementPanel from '../components/TreePlacementPanel';
import ComparisonPanel from '../components/ComparisonPanel'
import { circleMetres } from '../utils/geo';
import { useTreeCanopy } from '../hooks/canopy';
import { START_PITCH, START_BEARING } from '../config/mapConfig';

export default function PlantTreePage({ planTarget, onDone }) {
    const mapRef = useRef(null);
    const debounceRef = useRef(null);

    const simulation = useTreeSimulation();
    const trees = useTreeCanopy();

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

    const handleConfirm = useCallback(() => {
        const center = mapRef.current?.getMap()?.getCenter();
        if (center) simulation.placeTree(center.lng, center.lat);
    }, [simulation]);

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
            properties: {},
            geometry: circleMetres(t.lng, t.lat, t.radiusM),
        })),
    }), [simulation.trees])

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
                    mapboxAccessToken={import.meta.env.VITE_MAPBOX_ACCESS_TOKEN}
                    initialViewState={{
                    longitude: planTarget?.lng ?? 145.13,
                    latitude: planTarget?.lat ?? -37.918,
                    zoom: 18.2,
                    pitch: START_PITCH,
                    bearing: START_BEARING,
                    }}
                    config={{ basemap: { lightPreset: 'day' } }}
                    style={{ width: '100%', height: '100%' }}
                    mapStyle="mapbox://styles/mapbox/standard"
                >
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
                    </Source>
                    )}
                </Map>

                {simulation.active && (
                    <div className={styles['crosshair-overlay']}>
                    <div className={panelStyles['crosshair']} />
                    </div>
                )}

                <div className={styles['pilot-badge']}>Simulation is indicative, not professional advice</div>
                </div>

                <aside className={styles['plant-sidebar']}>
                    {simulation.trees.length > 0 && projected && !simulation.active ? (
                        <ComparisonPanel
                            baseline={{ pct: trees.pct }}
                            projected={projected}
                            trees={simulation.trees}
                            onAdd={simulation.startPlanting}
                            onReset={simulation.removeAllTree}
                            onRemoveTree={simulation.removeTreeAt}
                            onFinish={handleFinish}
                        />
                    ) : (
                        <TreePlacementPanel
                            size={simulation.size}
                            onSizeChange={simulation.setSize}
                            onConfirm={handleConfirm}
                            onCancel={handleDiscard}
                            hasPosition={simulation.trees.length > 0}
                        />
                    )}
                </aside>
            </div>
        </div>
    );
}