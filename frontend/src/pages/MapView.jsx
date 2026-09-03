import { useEffect, useRef, useState, useCallback } from 'react';

import Map, { Marker, Source, Layer } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
// import { SearchBox } from '@mapbox/search-js-react';
import styles from './MapView.module.css';
import { useParcels } from '../hooks/parcels';
import { useTreeCanopy } from '../hooks/canopy';
import { useSelectedProperty } from "../hooks/property";
import { circleMetres, centroidOfGeometry } from '../utils/geo';

import SidePanel from '../components/SidePanel';
import PropertyPanel from "../components/PropertyPanel";
import AddressAutocomplete from "../components/AddressAutocomplete";
import { START_ZOOM, MIN_PARCEL_ZOOM } from "../config/mapConfig";

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



export default function MapView({ selectedLocation, setSelectedLocation, simulatedTrees, onPlantTree }) {
    const mapRef = useRef(null);
    const hoverId = useRef(null);
    const debounceRef = useRef(null);
    const consumedInitialLocation = useRef(false);

    const [zoom, setZoom] = useState(START_ZOOM);
    const [propertyAnchor, setPropertyAnchor] = useState(null)
    
    const trees = useTreeCanopy();
    const parcels = useParcels();
    const propertySelected = useSelectedProperty(trees.treeFeatures);
    const { resolveFromBaseline } = propertySelected;

    
    const [addressInput, setAddressInput] = useState(selectedLocation?.address || "");
    const [markerCoordinates, setMarkerCoordinates] = useState(selectedLocation?.coordinates
            ? { longitude: selectedLocation.coordinates[0], latitude: selectedLocation.coordinates[1] }
            : null);
    const [isMapLoaded, setIsMapLoaded] = useState(false);
    


    const transitCoordinates = useCallback((longitude, latitude) => {
        mapRef.current?.flyTo({
            center: [longitude, latitude],
            zoom: 18,
            duration: 2000,
        });
        setMarkerCoordinates({ latitude, longitude });
        setPropertyAnchor({ lng: longitude, lat: latitude });
    }, []);

    const flyToFeature = useCallback((result) => {
        const geom = result?.feature?.geometry;
        if (!geom) return;
        const centroid = centroidOfGeometry(geom);
        if (centroid) transitCoordinates(centroid.lng, centroid.lat);
    }, [transitCoordinates]);

    const handleAddressSelect = async (location) => {
        setSelectedLocation({ address: location.full_address, addressId: location.address_id });
        setAddressInput(location.full_address);
        flyToFeature(await resolveFromBaseline(location.full_address));
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
        trees.refresh(bounds, centerLat, zoom);
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
        consumedInitialLocation.current = false;
    }, [selectedLocation?.addressId]);

    useEffect(() => {
        if (!isMapLoaded || !selectedLocation?.address || consumedInitialLocation.current) return;
        consumedInitialLocation.current = true;
        let cancelled = false;
        resolveFromBaseline(selectedLocation.address).then((result) => {
            if (!cancelled) flyToFeature(result);
        });
        return () => { cancelled = true; };
}, [isMapLoaded, selectedLocation, resolveFromBaseline, flyToFeature]);

    return (
        <div className={styles["map-container"]}>
            <div className={styles["address-container"]}>
                <div className={styles["search-box-container"]}>
                    {/* <SearchBox
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
                    /> */}
                    <AddressAutocomplete
                        value={addressInput}
                        onChange={handleAddressChange}
                        onSelect={handleAddressSelect}
                        placeholder="Search for an address"
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
                    zoom: 10,
                    pitch: 45,
                    bearing: -17.6
                }}
                config={{
                    basemap: {
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

                {simulatedTrees?.length > 0 && (
                    <Source
                        id="simulated-trees"
                        type="geojson"
                        data={{
                            type: 'FeatureCollection',
                            features: simulatedTrees.map((t) => ({
                                type: 'Feature',
                                properties: {},
                                geometry: circleMetres(t.lng, t.lat, t.radiusM),
                            })),
                        }}
                    >
                        <Layer id="simulated-trees-fill" type="fill" source="simulated-trees" paint={{ 'fill-color': '#2F7D5A', 'fill-opacity': 0.35 }} />
                        <Layer id="simulated-trees-line" type="line" source="simulated-trees" paint={{ 'line-color': '#2F7D5A', 'line-width': 2, 'line-dasharray': [2, 2] }} />
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

                {markerCoordinates && (
                    <Marker latitude={markerCoordinates.latitude} longitude={markerCoordinates.longitude} anchor="bottom">
                        <div className={styles['beacon-marker']}>
                            <div className={styles['beacon-pulse']} />
                            <div className={styles['beacon-pin']} />
                        </div>
                    </Marker>
                )}
            </Map>
            <SidePanel stats = {propertySelected.stats} trees={trees}/>
            
        </div>
        
    );
}



// Formal format for Document
// Function, errors, etc