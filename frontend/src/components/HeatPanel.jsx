import { useState } from "react"; // (2026-09-03) for the "?" disclosures
import styles from "./Panel.module.css";

const WEATHER_UNAVAILABLE = "unavailable_no_observation_within_3_hours";
const WEATHER_REGIONAL = "regional_context_warning";

// Heat section (2026-09-03, review #5/#12/#13): the band (heat_classification) leads, the
// temperature is the supporting number, and each "?" opens the database's own limitations
// wording instead of a hand-written paraphrase. The original component is kept below as a comment.
const SCOPE_LABEL = {
    relative_to_greater_melbourne_application_ready_baseline: "for Greater Melbourne",
};
const BAND_CLASS = { High: "band-high", Medium: "band-medium", Low: "band-low" };

export default function HeatPanel({ stats }) {
    const [open, setOpen] = useState(null); // "heat" | "air" | null
    if (!stats) {
        return null; // nothing selected yet — SidePanel is always mounted, so bail quietly
    }
    const band = stats.heatClassification || "Unavailable";
    const scope = SCOPE_LABEL[stats.classificationScope] || "";
    const heatNote = stats.limitations?.heat;
    const airNote = stats.limitations?.air_temperature;
    const airUnavailable = stats.weatherContext === WEATHER_UNAVAILABLE || stats.airTemperatureC == null;
    const toggle = (key) => setOpen((current) => (current === key ? null : key));
    const why = (key, label) => (
        <button
            type="button"
            className={styles["why-button"]}
            aria-expanded={open === key}
            aria-label={label}
            onClick={() => toggle(key)}
        >
            ?
        </button>
    );

    return (
        <div className={styles["heat-panel"]}>
            <div className={styles["heat-section"]}>
                <span className={styles["heat-section-label"]}>HEAT CONTEXT</span>
                {/* the address these numbers belong to: the searched address unless another lot was picked */}
                <p className={styles["heat-address"]}>Current address · {stats.address}</p>

                <div className={styles["band-lead"]}>
                    <span className={`${styles["band"]} ${styles[BAND_CLASS[band] || "band-na"]}`}>{band}</span>
                    {scope && <span className={styles["band-scope"]}>{scope}</span>}
                    {heatNote && why("heat", "Why this heat value")}
                </div>
                {open === "heat" && heatNote && (
                    <p className={styles["why-note"]}>
                        <span className={styles["why-key"]}>limitations.heat</span>
                        {heatNote}
                    </p>
                )}

                <dl className={styles["lot-rows"]}>
                    <dt>Land surface temperature</dt>
                    <dd>{stats.landSurfaceTempC != null ? `${stats.landSurfaceTempC.toFixed(1)}°C` : "—"}</dd>
                    <dt>
                        Air temperature
                        {airUnavailable && airNote && why("air", "Why air temperature is unavailable")}
                    </dt>
                    <dd>
                        {airUnavailable
                            ? <span className={`${styles["band"]} ${styles["band-na"]}`}>Unavailable</span>
                            : `${stats.airTemperatureC.toFixed(1)}°C`}
                    </dd>
                </dl>
                {stats.landSurfaceTempDate && (
                    <p className={styles["heat-caveat"]}>Measured {stats.landSurfaceTempDate} · Landsat land surface</p>
                )}
                {open === "air" && airUnavailable && airNote && (
                    <p className={styles["why-note"]}>
                        <span className={styles["why-key"]}>limitations.air_temperature</span>
                        {airNote}
                    </p>
                )}

                {stats.weatherContext === WEATHER_REGIONAL && (
                    <p className={styles["heat-caveat"]}>
                        Nearest station ({stats.weatherStationName}, {stats.weatherDistanceKm?.toFixed(1)}km)
                        is regional context only.
                    </p>
                )}
                {!airUnavailable && stats.weatherContext !== WEATHER_REGIONAL && stats.weatherStationName && (
                    <p className={styles["heat-caveat"]}>
                        {stats.weatherStationName}
                        {stats.weatherObservedAt && `, observed ${stats.weatherObservedAt}`}
                        {stats.weatherDistanceKm != null && ` (${stats.weatherDistanceKm.toFixed(1)}km away)`}.
                    </p>
                )}

                {stats.classificationScope && (
                    <p className={styles["heat-scope"]}>
                        Band relative to the Greater Melbourne application-ready baseline
                        {stats.classificationSchemeVersion ? ` · ${stats.classificationSchemeVersion}` : ""}
                    </p>
                )}
            </div>
        </div>
    );
}

// ---- original component (before 2026-09-03), kept for reference ----
// export default function HeatPanel({ stats }) {
    // if (!stats) {
        // return null; // nothing selected yet — SidePanel is always mounted, so bail quietly
    // }
    // return (
        // <div className={styles["heat-panel"]}>
            // {(stats.landSurfaceTempC != null && stats.landSurfaceTempC !== undefined) && (
                // <div className={styles["heat-section"]}>
                    // <span className={styles["heat-section-label"]}>HEAT CONTEXT</span>
                    // <dl className={styles["lot-rows"]}>
                        // {stats.landSurfaceTempC != null && (
                            // <>
                                // <dt>Land surface temp</dt>
                                // <dd>{stats.landSurfaceTempC.toFixed(1)}°C</dd>
                            // </>
                        // )}
                        // {stats.weatherContext !== WEATHER_UNAVAILABLE && stats.airTemperatureC != null && (
                            // <>
                                // <dt>Nearby air temp</dt>
                                // <dd>{stats.airTemperatureC.toFixed(1)}°C</dd>
                            // </>
                        // )}
                    // </dl>

                    // {/* Required disclaimer per README — LST is never the same
                        // measurement as air temperature. */}
                    // {stats.landSurfaceTempC != null && (
                        // <p className={styles["heat-caveat"]}>
                            // Land surface temperature, not the air temperature a resident experiences.
                            // {stats.landSurfaceTempDate && ` Measured ${stats.landSurfaceTempDate}.`}
                        // </p>
                    // )}

                    // {stats.weatherContext === WEATHER_REGIONAL && (
                        // <p className={styles["heat-caveat"]}>
                            // Nearest station ({stats.weatherStationName}, {stats.weatherDistanceKm?.toFixed(1)}km)
                            // is regional context only.
                        // </p>
                    // )}
                    // {stats.weatherContext === WEATHER_UNAVAILABLE && (
                        // <p className={styles["heat-caveat"]}>
                            // No weather observation within the last 3 hours.
                        // </p>
                    // )}
                    // {stats.weatherContext && stats.weatherContext !== WEATHER_REGIONAL && stats.weatherContext !== WEATHER_UNAVAILABLE && stats.weatherStationName && (
                        // <p className={styles["heat-caveat"]}>
                            // {stats.weatherStationName}
                            // {stats.weatherObservedAt && `, observed ${stats.weatherObservedAt}`}
                            // {stats.weatherDistanceKm != null && ` (${stats.weatherDistanceKm.toFixed(1)}km away)`}.
                        // </p>
                    // )}
                // </div>
            // )}
        // </div>
    // )
// }
