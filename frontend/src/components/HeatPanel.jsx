import styles from "./Panel.module.css";

const WEATHER_UNAVAILABLE = "unavailable_no_observation_within_3_hours";
const WEATHER_REGIONAL = "regional_context_warning";

export default function HeatPanel({ stats }) {
    if (!stats) {
        return null; // nothing selected yet — SidePanel is always mounted, so bail quietly
    }
    return (
        <div className={styles["heat-panel"]}>
            {(stats.landSurfaceTempC != null && stats.landSurfaceTempC !== undefined) && (
                <div className={styles["heat-section"]}>
                    <span className={styles["heat-section-label"]}>HEAT CONTEXT</span>
                    <dl className={styles["lot-rows"]}>
                        {stats.landSurfaceTempC != null && (
                            <>
                                <dt>Land surface temp</dt>
                                <dd>{stats.landSurfaceTempC.toFixed(1)}°C</dd>
                            </>
                        )}
                        {stats.weatherContext !== WEATHER_UNAVAILABLE && stats.airTemperatureC != null && (
                            <>
                                <dt>Nearby air temp</dt>
                                <dd>{stats.airTemperatureC.toFixed(1)}°C</dd>
                            </>
                        )}
                    </dl>

                    {/* Required disclaimer per README — LST is never the same
                        measurement as air temperature. */}
                    {stats.landSurfaceTempC != null && (
                        <p className={styles["heat-caveat"]}>
                            Land surface temperature, not the air temperature a resident experiences.
                            {stats.landSurfaceTempDate && ` Measured ${stats.landSurfaceTempDate}.`}
                        </p>
                    )}

                    {stats.weatherContext === WEATHER_REGIONAL && (
                        <p className={styles["heat-caveat"]}>
                            Nearest station ({stats.weatherStationName}, {stats.weatherDistanceKm?.toFixed(1)}km)
                            is regional context only.
                        </p>
                    )}
                    {stats.weatherContext === WEATHER_UNAVAILABLE && (
                        <p className={styles["heat-caveat"]}>
                            No weather observation within the last 3 hours.
                        </p>
                    )}
                    {stats.weatherContext && stats.weatherContext !== WEATHER_REGIONAL && stats.weatherContext !== WEATHER_UNAVAILABLE && stats.weatherStationName && (
                        <p className={styles["heat-caveat"]}>
                            {stats.weatherStationName}
                            {stats.weatherObservedAt && `, observed ${stats.weatherObservedAt}`}
                            {stats.weatherDistanceKm != null && ` (${stats.weatherDistanceKm.toFixed(1)}km away)`}.
                        </p>
                    )}
                </div>
            )}
        </div>
    )
}