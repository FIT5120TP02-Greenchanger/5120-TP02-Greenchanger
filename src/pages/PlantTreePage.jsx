import { useRef, useCallback, useEffect } from 'react';
import Map, { Source, Layer } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import styles from './PlantTreePage.module.css';
import panelStyles from '../components/Panel.module.css';
import { useTreeSimulation } from '../hooks/simulation';
import TreePlacementPanel from '../components/TreePlacementPanel';
import { circleMetres } from '../utils/geo';
import { START_PITCH, START_BEARING } from '../config/mapConfig';

export default function PlantTreePage({ planTarget, onDone }) {
    const mapRef = useRef(null);
    const simulation = useTreeSimulation();

    useEffect(() => {
        simulation.startPlanting();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const handleConfirm = useCallback(() => {
        const center = mapRef.current?.getMap()?.getCenter();
        if (center) simulation.placeTree(center.lng, center.lat);
    }, [simulation]);

    const handleFinish = useCallback(() => {
        onDone(simulation.position ? { ...simulation.position, radiusM: simulation.radiusM } : null);
    }, [simulation, onDone]);

    return (
        <div className={styles['plant-page']}>
        <header className={styles['plant-header']}>
            <div className={styles['brand']}>
            <span className={styles['brand-dot']} />
            <span>GreenChanger</span>
            </div>
            <span className={styles['step-indicator']}>1 / 1</span>
        </header>

        <div className={styles['plant-body']}>
            <div className={styles['map-area']}>
            <Map
                ref={mapRef}
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
                {simulation.position && (
                <Source
                    id="simulated-tree"
                    type="geojson"
                    data={{
                    type: 'Feature',
                    properties: {},
                    geometry: circleMetres(simulation.position.lng, simulation.position.lat, simulation.radiusM),
                    }}
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
                {simulation.position && !simulation.active ? (
                    <div className={panelStyles['placement-panel']}>
                        <span>SIMULATE ONE TREE</span>
                        <h3>Tree placed</h3>
                        <p>You can reposition, resize, or remove it.</p>
                        <button className={panelStyles['place-button']} onClick={simulation.repositionTree}>
                            Reposition
                        </button>
                        <button className={panelStyles['cancel-button']} onClick={simulation.removeTree}>
                            Remove tree
                        </button>
                        <button className={panelStyles['place-button']} onClick={handleFinish}>
                            Done
                        </button>
                    </div>
                ) : (
                    <TreePlacementPanel
                    size={simulation.size}
                    onSizeChange={simulation.setSize}
                    onConfirm={handleConfirm}
                    onCancel={() => onDone(null)}
                    hasPosition={!!simulation.position}
                    />
                )}
            </aside>
        </div>
        </div>
    );
}