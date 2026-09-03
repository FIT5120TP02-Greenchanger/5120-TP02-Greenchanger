import styles from './Panel.module.css';
import { TREE_SIZES } from '../hooks/simulation';

// export default function TreePlacementPanel({ size, onSizeChange, onConfirm, onCancel, hasPosition }) {
// canPlant added (2026-09-03): the button waits until the user has clicked a spot on the map
export default function TreePlacementPanel({ size, onSizeChange, onConfirm, onCancel, hasPosition, canPlant }) {
    return (
        <div className={styles['placement-panel']}>
            <span>SIMULATE ONE TREE</span>
            {/* <h3>Choose one point</h3> */}
            {/* <p>Place a simulated tree on the map.</p> */}
            <h3>Place your tree</h3>
            <p>The dashed circle is the canopy at maturity. Click on the map to put it where you want.</p>

            <div className={styles['placement-step']}>
                {/* <strong>1. Select a map point</strong> */}
                {/* <p>Only one active simulated tree.</p> */}
                <strong>Choose a size, then click on the map where you want the tree.</strong>
                <p>The circle resizes to match the tree. Click again to move it.</p>
                <p>No suitability assessment is provided.</p>
            </div>

            <div className={styles['tree-options-container']}>
                {Object.entries(TREE_SIZES).map(([label, { heightLabel, price }]) => (
                <div
                    key={label}
                    className={size === label ? styles.selected : ''}
                    onClick={() => onSizeChange(label)}
                >
                    <h4>{label}</h4>
                    <p>{heightLabel}</p>
                    <p>{price}</p>
                </div>
                ))}
            </div>

            <button className={styles['place-button']} onClick={onConfirm} disabled={canPlant === false}>
                {/* {hasPosition ? 'Place here?' : 'Place simulated tree'} */}
                {hasPosition ? 'Plant another here' : 'Plant here'}
            </button>
            <p className={styles['placement-hint']}>You can reposition or remove it later.</p>
            <button className={styles['cancel-button']} onClick={onCancel}>Cancel</button>
        </div>
    );
}