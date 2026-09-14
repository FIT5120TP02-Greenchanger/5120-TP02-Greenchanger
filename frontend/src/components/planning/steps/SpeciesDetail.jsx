import { useState } from 'react'
import styles from '../TreePlantingFlow.module.css'
import { TREE_SIZES } from '../../../hooks/simulation'

export default function SpeciesDetail({ species, size, onSizeChange, onApply, onBack, onExit }) {
    const [treeSize, setTreeSize] = useState('Small')
    if (!species) return null
    return (
        <div className={styles['species-detail']}>
            <h3>{species.commonName} selected</h3>
            <img src={species.image} width={120} height={120} />
            <div>
                <span>CHOOSE PLANTING SIZE</span>
                <h1>{treeSize} · {treeSize === 'Small' ? '1.5-2m' : (treeSize === 'Medium' ? '4-5m' : '8-10m')}</h1>
                <div className={styles['price-container']}>
                    {Object.entries(TREE_SIZES).map(
                        ([label, { heightLabel, radiusM }]) => (
                                <p 
                                key={label} 
                                onClick={() => {
                                        onSizeChange(label)
                                        setTreeSize(label)
                                    }
                                }>
                                    {label[0]} ${species.price[label]}
                                </p>
                            )
                        )}
                </div>
            </div>
            <button className={styles['back-button']} onClick={onBack}>Back</button>
            <button className={styles['apply-button']} onClick={onApply} disabled={!size}>Apply</button>
            <button className={styles['exit-button']} onClick={onExit}>Exit</button>
        </div>
    )
}