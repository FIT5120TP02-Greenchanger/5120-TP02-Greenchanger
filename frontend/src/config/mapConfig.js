/* ============================================================
   1 · CONFIG — put your own Mapbox token here
   Get one free at https://account.mapbox.com/access-tokens/
   ============================================================ */

export const CLAYTON = [145.1300, -37.9180]; // lng, lat
export const START_ZOOM = 16.4;
export const START_PITCH = 58;
export const START_BEARING = -24;

// Vicmap tree points — keyless public ArcGIS REST, CC-BY 4.0.
// Per-tree canopy_radius_m and height_m. Covers all of metro Melbourne.
export const TREES_URL =
    "https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/ArcGIS/rest/services/" +
    "Vicmap_Vegetation_Tree_Urban/FeatureServer/0/query";

export const MIN_TREE_HEIGHT = 3; // matches the DEECA PerAnyTree definition

export const PARCELS_URL =
    "https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/ArcGIS/rest/services/" +
    "Vicmap_Property/FeatureServer/0/query";

// Below this zoom a viewport holds more than the 2000-record cap, so the
// boundaries would be silently incomplete. Better to show none.
export const MIN_TREE_ZOOM = 15.5;
export const MIN_PARCEL_ZOOM = 15.5;

export const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN;

// GreenShift data-team backend. Ask them for the deployed URL.
export const API_BASE_URL = import.meta.env.VITE_GREENSHIFT_API_URL;
