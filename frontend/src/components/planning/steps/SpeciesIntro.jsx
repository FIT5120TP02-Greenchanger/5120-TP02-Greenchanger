import styles from '../TreePlantingFlow.module.css';

export default function SpeciesIntro({ onExplore, onExit, nTrees, canopyM2, viewM2 }) {
    return (
        <div className={styles['species-intro']}>
            <span>CHOOSE A TREE SPECIES</span>
            <p>Compare suitable tree types before adding one to your Melbourne scenario.</p>

            <div className={styles["canopy-view"]}>
                <span>WHAT IS HERE NOW</span>
                <dl className={styles["canopy-stats"]}>
                    <dt>Trees</dt>
                    <dd>{nTrees.toLocaleString()}</dd>
                    <dt>Canopy area</dt>
                    <dd>{canopyM2.toFixed(0) + ' m²'}</dd>
                    <dt>View area</dt>
                    <dd>{viewM2.toFixed(0) + ' m²'}</dd>
                </dl>
            </div>

            <button className={styles['explore-button']} onClick={onExplore}>Explore species</button>
            <p>Information is illustrative, not professional planting advice. Check local council guidance.</p>
            <button className={styles['exit-button']} onClick={onExit}>Exit</button>
        </div>
    );
}