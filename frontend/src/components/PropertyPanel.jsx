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
            {onClose && (
                <button type="button" className={styles["lot-close"]} onClick={onClose} aria-label="Close">×</button>
            )}
            <p>{stats.address.split(',')[0]}</p>
            <dl className={styles["lot-rows"]}>
                <dt>Lot area</dt>
                <dd>{stats.areaLabel}</dd>
                <dt>Trees on lot</dt>
                <dd>{stats.treeCount}</dd>

                {stats.neighbourhoodCanopyPct != null && (
                    <>
                        <dt>Neighbourhood canopy</dt>
                        <dd>{stats.neighbourhoodCanopyPct.toFixed(1)}%</dd>
                    </>
                )}
                {/* {stats.canopyClassification && (
                    <>
                        <dt>Classification</dt>
                        <dd>{stats.canopyClassification}</dd>
                    </>
                )} */}
            </dl>
            
            <button className={styles["plant-button"]} onClick={onPlantTree}>Plant a tree here</button>
        </div>
    );
}