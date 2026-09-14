import styles from '../TreePlantingFlow.module.css'
import { TREE_SIZES } from '../../../hooks/simulation'

export default function SpeciesDetail({ species, size, onSizeChange, onApply, onBack, onExit }) {
    if (!species) return null
    return (
        <div className={styles['species-detail']}>
            <span>CHOOSE A SIZE</span>
            <h3>{species.commonName}</h3>
            <div className={styles['tree-options-container']}>
                {Object.entries(TREE_SIZES).map(([label, { heightLabel, price }]) => (
                    <div key={label} className={size === label ? styles.selected : ''} onClick={() => onSizeChange(label)}>
                        <h4>{label}</h4>
                        <p>{heightLabel}</p>
                        <p>{price}</p>
                    </div>
                ))}
            </div>
            <button className={styles['back-button']} onClick={onBack}>Back</button>
            <button className={styles['apply-button']} onClick={onApply} disabled={!size}>Apply</button>
            <button className={styles['exit-button']} onClick={onExit}>Exit</button>
        </div>
    )
}