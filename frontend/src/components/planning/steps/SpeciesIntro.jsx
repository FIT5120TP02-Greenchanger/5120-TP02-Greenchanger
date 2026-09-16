import styles from '../TreePlantingFlow.module.css';

export default function SpeciesIntro({ onExplore, onExit, nTrees, canopyM2, viewM2, canExplore }) {
    const hasTreeCount = Number.isFinite(nTrees)
    const hasCanopy = Number.isFinite(canopyM2)
    const canopyShare = hasCanopy && Number.isFinite(viewM2) && viewM2 > 0
        ? ((canopyM2 / viewM2) * 100).toFixed(1)
        : null
    return (
        <div className={styles['panel-body']}>
            <span className={styles['user-note']}>CHOOSE A TREE SPECIES</span>
            <h2 className={styles['panel-title']}>Add a tree to your scenario</h2>
            <p>Compare suitable tree types before adding one to your Melbourne scenario.</p>

            {(hasTreeCount || hasCanopy) && (
                // <div className={styles['intro-stats']}>
                //     {hasTreeCount && (
                //         <div className={styles['intro-stat']}>
                //             <span className={styles['intro-stat-label']}>Trees in view</span>
                //             <span className={styles['intro-stat-value']}>{nTrees.toLocaleString()}</span>
                //         </div>
                //     )}
                //     {hasCanopy && (
                //         <div className={styles['intro-stat']}>
                //             <span className={styles['intro-stat-label']}>Canopy in view</span>
                //             <span className={styles['intro-stat-value']}>
                //                 {Math.round(canopyM2).toLocaleString()} m²{canopyShare ? ` · ${canopyShare}%` : ''}
                //             </span>
                //         </div>
                //     )}
                // </div>
                <div className={styles["intro-stats"]}>
                    <dl className={styles["intro-stat"]}>
                        {hasTreeCount && (
                            <dt className={styles['intro-stat-label']}>Trees in view</dt>
                        )}
                        {hasTreeCount && (
                            <dd className={styles['intro-stat-value']}>{nTrees.toLocaleString()}</dd>
                        )}
                        {hasCanopy && (
                            <dt className={styles['intro-stat-label']}>Canopy area</dt>
                        )}
                        {hasCanopy && (
                                <dd className={styles['intro-stat-value']}>{canopyM2.toFixed(0) + ' m²'}</dd>
                        )}
                        {hasCanopy && (
                            <dt className={styles['intro-stat-label']}>View area</dt>
                        )}
                        {hasCanopy && (
                            <dd className={styles['intro-stat-value']}>{viewM2.toFixed(0) + ' m²'}</dd>
                        )}
                    </dl>
                </div>
            )}
            <p className={styles['note']}>Information is illustrative, not professional planting advice. Check local council guidance.</p>
            <div className={styles['panel-actions']}>
                {!canExplore && (
                    <p className={styles['placement-hint']}>Click on the map to choose a spot first.</p>
                )}
                <div className={styles['panel-footer']}>
                    <button type="button" className={styles['exit-button']} onClick={onExit}>
                        Exit
                    </button>
                    <button
                        type="button"
                        className={styles['explore-button']}
                        onClick={onExplore}
                        disabled={!canExplore}
                    >
                        Explore species
                    </button>
                </div>
            </div>
        </div>
    );
}