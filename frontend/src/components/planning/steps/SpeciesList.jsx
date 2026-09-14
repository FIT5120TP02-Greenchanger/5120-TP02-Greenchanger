import styles from '../TreePlantingFlow.module.css';
export default function SpeciesList({ species, onSelect, onBack, onExit, onViewDetail }) {
    return (
        <div className={styles['species-list']}>
            <span>EXPLORE TREE SPECIES</span>
            <p>Appearance and size are illustrative at maturity.</p>
            <ul>
                {species.map((s) => (
                    <li key={s.id} onClick={() => onSelect(s)}>
                        <img src={s.image} alt={s.commonName} />
                        <span>{s.commonName}</span>
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