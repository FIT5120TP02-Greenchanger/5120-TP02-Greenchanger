import styles from './PlantModeChooser.module.css'
export default function PlantModeChooser({ onQuickSimulation, onExploreSpecies, onCancel }) {
    return (
        <div className={styles["plant-mode-chooser"]}>
            <span className={styles['chooser-label']} href="#" onClick={(e) => { e.preventDefault(); onCancel(); }}>Plant a tree</span>
            <h3 className={styles['chooser-title']}>How would you like to explore?</h3>
            <p className={styles['chooser-intro']}>Try a quick canopy simulation, or choose a tree species.</p>

            <button className={`${styles['mode-option']} ${styles['mode-option--quick']}`} onClick={onQuickSimulation}>
                <strong>Quick simulation</strong>
                <p>Choose a canopy size and preview one tree's impact.</p>
            </button>

            <button className={`${styles['mode-option']} ${styles['mode-option--species']}`} onClick={onExploreSpecies}>
                <strong>Explore tree species</strong>
                <p>Choose a species, view details, and personalise your tree.</p>
            </button>

            <p className={styles['chooser-hint']}>Planning preview only. Prices are not yet verified.</p>
            <button className={styles['chooser-cancel']} onClick={onCancel}>Cancel</button>
        </div>
    );
}