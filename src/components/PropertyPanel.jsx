import styles from './Panel.module.css'

export default function PropertyPanel({ stats, hint, onPlantTree }) {
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
            <p>{stats.address.split(',')[0]}</p>
            <dl className={styles["lot-rows"]}>
                <dt>Lot area</dt>
                <dd>{stats.areaLabel}</dd>
                <dt>Trees on lot</dt>
                <dd>{stats.treeCount}</dd>
            </dl>
            <button className={styles["plant-button"]} onClick={onPlantTree}>Plant a tree here</button>
        </div>
    );
}