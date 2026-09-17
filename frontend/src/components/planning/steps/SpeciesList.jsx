import styles from '../TreePlantingFlow.module.css'

export default function SpeciesList({ species = [], selectedSpecies, onSelect, onViewDetail, onBack, onExit }) {
    return (
        <>
            <div className={styles['panel-body']}>
                <span className={styles['user-note']}>Explore tree species</span>
                <h2 className={styles['panel-title']}>Pick a species to compare</h2>
                <p className={styles['subtitle']}>Appearance and size are illustrative at maturity.</p>

                <ul className={styles['species-list']}>
                    {species.map((s) => {
                        const isSelected = selectedSpecies?.id === s.id
                        return (
                            <li key={s.species_key} onClick={() => onSelect(s)}>
                                <button
                                    type="button"
                                    aria-pressed={isSelected}
                                    className={`${styles['species-card']} ${isSelected && styles['species-card--selected']}`}
                                >
                                    <img
                                        className={styles['species-card-image']}
                                        src={s.image_url}
                                        alt={s.image_alt_text}
                                        width={88}
                                        height={122}
                                        loading="lazy"
                                    />
                                    <span className={styles['species-card-text']}>
                                        <span className={styles['species-name']}>{s.common_name}</span>
                                        <span className={styles['species-latin']}>{s.scientific_name}</span>
                                    </span>
                                    <span className={styles['chevron']} aria-hidden="true">&rsaquo;</span>
                                </button>
                            </li>
                        )
                    })}
                </ul>

                <p className={styles['note']}>
                    Each species offers Small, Medium and Large stock.
                    <br />
                    Prices are indicative supply-only estimates.
                </p>
            </div>

            <div className={styles['panel-actions']}>
                <div className={styles['panel-footer']}>
                    <button type="button" className={styles['back-button']} onClick={onBack}>
                        Back
                    </button>
                    <button
                        type="button"
                        className={styles['detail-button']}
                        onClick={onViewDetail}
                        disabled={!selectedSpecies}
                    >
                        {selectedSpecies ? `Select ${selectedSpecies.common_name}` : 'Select a tree'}
                    </button>
                </div>
                <button type="button" className={styles['exit-button']} onClick={onExit}>
                    Exit
                </button>
            </div>
        </>
    )
}