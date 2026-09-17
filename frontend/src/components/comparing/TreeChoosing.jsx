import styles from './TreeChoosing.module.css'
import list_styles from '../planning/TreePlantingFlow.module.css'
export default function TreeChoosing({species, selectedSpecies, compareArray, setCompareArray, onBack, onCompareTree}) {
    function handleCheckbox(s) {
        setCompareArray(prev => {
            const alreadySelected = prev.some(
                item => item.species_key === s.species_key
            )

            if (alreadySelected) {
                return prev.filter(
                    item => item.species_key !== s.species_key
                )
            }

            return [...prev, s]
        })
    }
    return (
        <div>
            <div className={styles["panel-species-choosing"]}>
                <h2 className={styles['panel-title']}>{selectedSpecies?.common_name} on your lot</h2>
                <p>Select one or more species to compare</p>
                {species.map((s) => {
                    // const isSelected = selectedSpecies?.id === s.id
                    const isCompared = compareArray.some(
                        item => item.species_key === s.species_key
                    )
                    // the green frame follows the checkbox (species rows have no id, so the old test was always true)
                    const isSelected = isCompared
                    return (
                        <li key={s.species_key} onClick={() => {handleCheckbox(s);}} for={s.species_key}>
                            <button
                                aria-pressed={isSelected}
                                className={`${list_styles['species-card']} ${isSelected && list_styles['species-card--selected']}`}
                            >
                                <img
                                    className={list_styles['species-card-image']}
                                    src={s.image_url}
                                    alt={s.image_alt_text}
                                    width={88}
                                    height={122}
                                    loading="lazy"
                                />
                                <span className={list_styles['species-card-text']}>
                                    <span className={list_styles['species-name']}>{s.common_name}</span>
                                    <span className={list_styles['species-latin']}>{s.scientific_name}</span>
                                </span>
                                <input
                                    type="checkbox"
                                    className={styles['compare-checkbox']}
                                    name={s.species_key}
                                    id={s.species_key}
                                    checked={isCompared}
                                    onChange={() => handleCheckbox(s)}
                                    onClick={e => e.stopPropagation()}
                                />
                            </button>
                        </li>
                    )
                })}
            </div>
            <div className={list_styles['panel-actions']}>
                <div className={list_styles['panel-footer']}>
                    <button type="button" className={list_styles['back-button']} onClick={onBack}>
                        Back
                    </button>
                    <button
                        type="button"
                        className={list_styles['compare-button']}
                        onClick={onCompareTree}
                        disabled={!selectedSpecies}
                    >
                        Compare trees
                    </button>
                </div>
            </div>
        </div>
    )
}