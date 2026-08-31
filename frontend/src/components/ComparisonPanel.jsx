import styles from './Panel.module.css';

export default function ComparisonPanel({ baseline, projected, onReset, onNewScenario, onFinish }) {
    return (
        <div className={styles['scenario-panel']}>
            <span>SCENARIO COMPARISON</span>
            <h3>Current vs simulated</h3>

            <div className={styles['scenario-card']}>
                <span className={styles['scenario-card-label']}>CURRENT BASELINE</span>
                <div className={styles['scenario-card-pct']}>{baseline.pct.toFixed(1)}% canopy</div>
                <p className={styles['scenario-card-note']}>Prepared neighborhood result</p>
            </div>

            <div className={`${styles['scenario-card']} ${styles['scenario-card--simulated']}`}>
                <span className={styles['scenario-card-label']}>ONE SIMULATED TREE</span>
                <div className={styles['scenario-card-pct']}>{projected.pct.toFixed(1)}% canopy</div>
                <p className={styles['scenario-card-highlight']}>
                    {projected.deltaPts >= 0 ? '+' : ''}{projected.deltaPts.toFixed(1)} pts indicative canopy
                </p>
                <p className={styles['scenario-card-highlight']}>Shade potential: increased</p>
                <p className={styles['scenario-card-note']}>No precise temperature reduction claimed</p>
            </div>

            <div className={styles['assumptions-box']}>
                <span>ASSUMPTIONS &amp; LIMITATIONS</span>
                <p>Default mature canopy; directional impact only.</p>
            </div>

            <div className={styles['scenario-actions']}>
                <button className={styles['reset-button']} onClick={onReset}>Reset</button>
                <button className={styles['new-scenario-button']} onClick={onNewScenario}>New scenario</button>
            </div>
            <button className={styles['place-button']} onClick={onFinish}>Done</button>
        </div>
    );
}
