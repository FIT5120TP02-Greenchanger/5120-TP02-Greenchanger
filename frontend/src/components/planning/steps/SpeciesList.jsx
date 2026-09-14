import styles from '../TreePlantingFlow.module.css';
import { TREE_SIZES } from '../../../hooks/simulation';
const SIZE_INDEX = {
    Small: 0,
    Medium: 1,
    Large: 2,
}
export default function SpeciesList({ species, onSelect, onBack, onExit, onViewDetail }) {
    return (
        <div className={styles['species-list']}>
            <span>EXPLORE TREE SPECIES</span>
            <p>Appearance and size are illustrative at maturity.</p>
            <ul>
                {species.map((s) => (
                    <li key={s.id} onClick={() => onSelect(s)}>
                        <img src={s.image} alt={s.commonName} width={120} height={120} />
                        <span>{s.commonName}</span>
                        <p>Choose size</p>
                        <div className={styles['price-container']}
                        // onClick={(e) => {
                        //     e.stopPropagation();
                        //     onSizeChange(label);
                        // }}
                        >
                        {Object.entries(TREE_SIZES).map(
                            ([label, { heightLabel, radiusM }]) => (
                                    <p key={label}>{label[0]} ${s.price[label]}</p>
                                )
                            )}
                        </div>
                    </li>
                ))}
            </ul>
            <p>Each species offers Small, Medium and Large stock.</p>
            <p>Prices are indicative supply only estimates.</p>
            <button className={styles['back-button']} onClick={onBack}>Back</button>
            <button className={styles['detail-button']} onClick={onViewDetail}>View Details</button>
            <button className={styles['exit-button']} onClick={onExit}>Exit</button>
        </div>
    );
}