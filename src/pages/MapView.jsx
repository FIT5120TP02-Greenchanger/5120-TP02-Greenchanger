import { useEffect, useRef, useState, useCallback } from 'react';

import Map, { Marker, Source, Layer } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import { SearchBox } from '@mapbox/search-js-react';
import styles from './MapView.module.css';
import { useParcels } from '../hooks/parcels';
import { useTreeCanopy } from '../hooks/canopy';
import { useSelectedProperty } from "../hooks/property";
import { circleMetres } from '../utils/geo';

import SidePanel from '../components/SidePanel';
import PropertyPanel from "../components/PropertyPanel";
import { START_ZOOM, START_PITCH, START_BEARING, MIN_PARCEL_ZOOM } from "../config/mapConfig";

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

const parcelHitLayer = {
    id: "parcel-hit",
    type: "fill",
    paint: {
        "fill-color": "#2F7D5A",
        "fill-opacity": ["case", ["boolean", ["feature-state", "hover"], false], 0.16, 0.01],
    },
};

const parcelLineLayer = {
    id: "parcel-line",
    type: "line",
    paint: {
        "line-color": "#2F7D5A",
        "line-width": ["case", ["boolean", ["feature-state", "hover"], false], 2, 0.8],
        "line-opacity": ["case", ["boolean", ["feature-state", "hover"], false], 0.9, 0.35],
    },
};

const lotFillLayer = { id: "lot-fill", type: "fill", paint: { "fill-color": "#2F7D5A", "fill-opacity": 0.2 } };
const lotLineLayer = {
    id: "lot-line",
    type: "line",
    paint: {
        "line-color": "#2F7D5A",
        "line-width": 3,
        "line-dasharray": ["case", ["==", ["get", "kind"], "circle"], ["literal", [2, 2]], ["literal", [1, 0]]],
    },
};



export default function MapView({ selectedLocation, setSelectedLocation, simulatedTree, onPlantTree }) {
    const mapRef = useRef(null);
    const hoverId = useRef(null);
    const debounceRef = useRef(null);
    const [zoom, setZoom] = useState(START_ZOOM);
    const [isPropertyclicked, setIsPropertyClick] = useState(false)
    const [propertyAnchor, setPropertyAnchor] = useState(null)
    
    const trees = useTreeCanopy();
    const parcels = useParcels();
    const propertySelected = useSelectedProperty(trees.treeFeatures);
    const { resolveFromCoordinates } = propertySelected;

    
    const [addressInput, setAddressInput] = useState(selectedLocation?.address || "");
    const [markerCoordinates, setMarkerCoordinates] = useState(selectedLocation?.coordinates
            ? { longitude: selectedLocation.coordinates[0], latitude: selectedLocation.coordinates[1] }
            : null);
    const [isMapLoaded, setIsMapLoaded] = useState(false);
    


    const transitCoordinates = useCallback((longitude, latitude) => {
        mapRef.current?.flyTo({
            center: [longitude, latitude],
            zoom: 17,
            duration: 2000,
        });
        setMarkerCoordinates({ latitude, longitude });
        setPropertyAnchor({ lng: longitude, lat: latitude });
    }, []);


    const handleAddressSelect = (location) => {
        const feature = location.features?.[0];
        if (!feature) return;
        const coordinates = feature.geometry?.coordinates;
        const label = feature.properties?.full_address || feature.properties?.name || '';

        setSelectedLocation({ address: label, coordinates });
        setAddressInput(label);
        transitCoordinates(coordinates[0], coordinates[1]);
        setPropertyAnchor({ lng: coordinates[0], lat: coordinates[1] });
        resolveFromCoordinates(coordinates[0], coordinates[1], { label })
    };


    const handleAddressChange = (location) => {
        setAddressInput(location);
    };


    const refreshAll = useCallback(() => {
        const map = mapRef.current?.getMap();
        if (!map) return;

        const bounds = map.getBounds();
        const centerLat = map.getCenter().lat;
        const zoom = map.getZoom();
        setZoom(zoom);
        trees.refresh(bounds, centerLat);
        parcels.refresh(bounds, zoom);
        console.log("Refreshed parcels and trees");
    }, [trees, parcels]);

    const handleMapLoad = () => {
        setIsMapLoaded(true);
        refreshAll();
    }

    const handleClick = useCallback(async (e) => {
        const map = mapRef.current?.getMap();
        if (!map) return;

        const features = map.queryRenderedFeatures(e.point, { layers: ["parcel-hit"] });
        setPropertyAnchor({ lng: e.lngLat.lng, lat: e.lngLat.lat });

        await propertySelected.selectAtPoint(features, parcels.parcelFeatures, zoom < MIN_PARCEL_ZOOM, e.lngLat);

        setIsPropertyClick(true);
    }, [propertySelected, parcels.parcelFeatures, zoom]);


    const handleMoveEnd = useCallback(() => {
        clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(refreshAll, 250);
    }, [refreshAll]);


    const handleMouseMove = useCallback((e) => {
        const map = mapRef.current?.getMap();
        if (!map || !e.features?.length) return;
        map.getCanvas().style.cursor = "pointer";
        if (hoverId.current !== null) {
        map.setFeatureState({ source: "parcels", id: hoverId.current }, { hover: false });
        }
        hoverId.current = e.features[0].id;
        map.setFeatureState({ source: "parcels", id: hoverId.current }, { hover: true });
    }, []);


    const handleMouseLeave = useCallback(() => {
        const map = mapRef.current?.getMap();
        if (!map) return;
        map.getCanvas().style.cursor = "";
        if (hoverId.current !== null) {
        map.setFeatureState({ source: "parcels", id: hoverId.current }, { hover: false });
        }
        hoverId.current = null;
    }, []);


    useEffect(() => {
        if (!isMapLoaded || !selectedLocation?.coordinates) return;
        const [lng, lat] = selectedLocation.coordinates;
        transitCoordinates(lng, lat);
        resolveFromCoordinates(lng, lat, { label: selectedLocation.address });
        console.log(propertyAnchor);
    }, [isMapLoaded, selectedLocation, transitCoordinates, resolveFromCoordinates]);
    

    return (
        <div className={styles["map-container"]}>
            <div className={styles["address-container"]}>
                <div className={styles["search-box-container"]}>
                    <SearchBox
                        accessToken={import.meta.env.VITE_MAPBOX_ACCESS_TOKEN}
                        onRetrieve={handleAddressSelect}
                        onChange={handleAddressChange}
                        value={addressInput}
                        placeholder="Search for an address"
                        options={{
                            country: 'AU',
                            language: 'en',
                            types: 'address',
                            bbox: [
                                144.4,
                                -38.3,
                                145.5,
                                -37.4
                            ]
                        }}
                        theme={{
                            variables: {
                                fontFamily: 'inherit',
                                fontSize: '16px',
                                borderRadius: '10px',
                            },
                            icons: {
                                search: ''
                            }
                        }}
                    />
                </div>
            </div>
            <Map
                ref={mapRef}
                onLoad={() => {handleMapLoad()}}
                onClick={handleClick}
                onMoveEnd={handleMoveEnd}
                onMouseMove={handleMouseMove}
                onMouseLeave={handleMouseLeave}
                mapboxAccessToken={import.meta.env.VITE_MAPBOX_ACCESS_TOKEN}
                initialViewState={{
                    latitude: -37.8136,
                    longitude: 144.9631,
                    zoom: 17,
                    pitch: 45,
                    bearing: -17.6
                }}
                config={{
                    basemap: {
                        show3dObjects: true,
                        show3dBuildings: true,
                        show3dLandmarks: true,
                        lightPreset: 'day'
                    }
                }}
                style={{ flex: 1, height: '100%' }}
                mapStyle="mapbox://styles/mapbox/standard"
                interactiveLayerIds={["parcel-hit"]}
            >

                <Source id="trees" type="geojson" data={{ type: 'FeatureCollection', features: trees.treeFeatures }}>
                    <Layer {...canopyLayer} source="trees" />
                </Source>

                <Source id="parcels" type="geojson" generateId data={{ type: 'FeatureCollection', features: parcels.parcelFeatures }}>
                    <Layer {...parcelHitLayer} source="parcels" />
                    <Layer {...parcelLineLayer} source="parcels" />
                </Source>

                <Source
                id="lot"
                type="geojson"
                data={
                    propertySelected.selected
                    ? { type: 'Feature', properties: propertySelected.selected.properties, geometry: propertySelected.selected.geometry }
                    : { type: 'FeatureCollection', features: [] }
                }
                >
                    <Layer {...lotFillLayer} source="lot" />
                    <Layer {...lotLineLayer} source="lot" />
                </Source>

                {simulatedTree && (
                    <Source
                        id="simulated-tree"
                        type="geojson"
                        data={{
                            type: 'Feature',
                            properties: {},
                            geometry: circleMetres(simulatedTree.lng, simulatedTree.lat, simulatedTree.radiusM),
                        }}
                    >
                        <Layer id="simulated-tree-fill" type="fill" source="simulated-tree" paint={{ 'fill-color': '#2F7D5A', 'fill-opacity': 0.35 }} />
                        <Layer id="simulated-tree-line" type="line" source="simulated-tree" paint={{ 'line-color': '#2F7D5A', 'line-width': 2, 'line-dasharray': [2, 2] }} />
                    </Source>
                )}

                {propertyAnchor && (
                    <Marker
                        longitude={propertyAnchor.lng}
                        latitude={propertyAnchor.lat}
                        anchor="bottom"
                        offset={[0, -50]}
                    >
                        <div className={styles["property-popup"]}>
                            <PropertyPanel 
                            stats={propertySelected.stats} 
                            hint={propertySelected.hint} 
                            onPlantTree={() => onPlantTree({
                                lng: propertyAnchor?.lng,
                                lat: propertyAnchor?.lat,
                                label: propertySelected.stats.address
                            })} />
                        </div>
                    </Marker>
                )}

                {propertyAnchor && (
                    <Marker longitude={propertyAnchor.lng} latitude={propertyAnchor.lat} anchor="bottom" offset={[0, -50]}>
                        <div className={styles['property-popup']}>
                            <PropertyPanel
                                stats={propertySelected.stats}
                                hint={propertySelected.hint}
                                onPlantTree={() =>
                                    onPlantTree({
                                        lng: propertyAnchor?.lng,
                                        lat: propertyAnchor?.lat,
                                        label: propertySelected.stats?.address,
                                    })
                                }
                            />
                        </div>
                    </Marker>
                )}
                {markerCoordinates && (
                    <Marker latitude={markerCoordinates.latitude} longitude={markerCoordinates.longitude} anchor="bottom">
                        <div className={styles['beacon-marker']}>
                            <div className={styles['beacon-pulse']} />
                            <div className={styles['beacon-pin']} />
                        </div>
                    </Marker>
                )}
            </Map>
            <SidePanel trees={trees}/>
            
        </div>
        
    );
}