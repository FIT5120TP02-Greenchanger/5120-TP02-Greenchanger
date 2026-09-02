import styles from './Panel.module.css';

export default function ComparisonPanel({ baseline, projected, trees, onAdd, onReset, onRemoveTree, onFinish }) {
    if(!baseline || !projected) return null;
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
                <span className={styles['scenario-card-label']}>
                    SIMULATED TREE{trees.length === 1 ? '' : 'S'}
                </span>
                <div className={styles['scenario-card-pct']}>{projected.pct.toFixed(1)}% canopy</div>
                <p className={styles['scenario-card-highlight']}>
                    {projected.deltaPts >= 0 ? '+' : ''}{projected.deltaPts.toFixed(1)} pts indicative canopy
                </p>
                <p className={styles['scenario-card-highlight']}>Shade potential: increased</p>
                <p className={styles['scenario-card-note']}>No precise temperature reduction claimed</p>
            </div>

            {trees.length > 0 && (
                <ul className={styles['tree-list']}>
                    {trees.map((t, i) => (
                        <li key={i} className={styles['tree-list-item']}>
                            <span>{t.size} tree</span>
                            <button
                                className={styles['tree-list-remove']}
                                onClick={() => onRemoveTree(i)}
                                aria-label={`Remove ${t.size} tree`}
                            >
                                x
                            </button>
                        </li>
                    ))}
                </ul>
            )}

            <div className={styles['assumptions-box']}>
                <span>ASSUMPTIONS &amp; LIMITATIONS</span>
                <p>Default mature canopy; directional impact only.</p>
            </div>

            <div className={styles['scenario-actions']}>
                <button className={styles['reset-button']} onClick={onReset}>Reset</button>
                <button className={styles['new-scenario-button']} onClick={onAdd}>+ Add tree</button>
            </div>
            <button className={styles['place-button']} onClick={onFinish}>Done</button>
        </div>
    );
}
