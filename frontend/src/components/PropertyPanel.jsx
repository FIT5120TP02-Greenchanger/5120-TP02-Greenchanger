import styles from './Panel.module.css'

// export default function PropertyPanel({ stats, hint, onPlantTree }) {
// onClose added (2026-09-03): the x button returns to the pinned-home view
export default function PropertyPanel({ stats, hint, onPlantTree, onClose }) {
    if (!stats) {
        return <p className={styles["lot-hint"]}>{hint || "Click any property to select it."}</p>;
    }

    return (
        <div
        className={styles["property-panel"]}
        onClick={(e) => e.stopPropagation()}
        onMouseDown={(e) => e.stopPropagation()}
        onMouseEnter={(e) => e.stopPropagation()}
        onMouseOver={(e) => e.stopPropagation()}
        onMouseMove={(e) => e.stopPropagation()}
        >
            <div className={styles["property-panel-header"]}>
                <p>{stats.address.split(',')[0]}</p>
                {onClose && (
                    <button type="button" className={styles["lot-close"]} onClick={onClose} aria-label="Close">×</button>
                )}
            </div>
            <div className={styles["property-stat-grid"]}>
                <div className={styles["property-stat-tile"]}>
                    <span className={styles["property-stat-label"]}>Lot area</span>
                    <strong className={styles["property-stat-value"]}>{stats.areaLabel.toFixed(0)}</strong>
                </div>
                <div className={styles["property-stat-tile"]}>
                    <span className={styles["property-stat-label"]}>Trees on lot</span>
                    <strong className={styles["property-stat-value"]}>{stats.treeCount}</strong>
                </div>
                {stats.propertyCanopyPct != null && (
                    <div className={`${styles["property-stat-tile"]} ${styles["property-stat-tile--full"]}`}>
                        <span className={styles["property-stat-label"]}>Property canopy</span>
                        <strong className={styles["property-stat-value"]}>{stats.propertyCanopyPct.toFixed(1)}%</strong>
                    </div>
                )}
            </div>
            <button className={styles["plant-button"]} onClick={onPlantTree}>Plant a tree here</button>
        </div>
    );
}