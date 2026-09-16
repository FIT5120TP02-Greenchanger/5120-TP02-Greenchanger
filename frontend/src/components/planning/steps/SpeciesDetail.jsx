import { useState, useEffect } from 'react'
import styles from '../TreePlantingFlow.module.css'
import { TREE_SIZES } from '../../../hooks/simulation'
import { fetchGrowth, fetchCosts, PREVIEW_AGE_YEARS } from '../../../services/trees'

export default function SpeciesDetail({ species, size, onSizeChange, setCompareArray, onApply, applying, onBack, onExit }) {
    const [growth, setGrowth] = useState(null)
    const [costs, setCosts] = useState(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)

    useEffect(() => {
        if (!species || !size) { setGrowth(null); setCosts(null); return }
        let cancelled = false
        setLoading(true)
        setGrowth(null)
        setCosts(null)
        setError(null)
        Promise.all([
            fetchGrowth({ species: species.scientific_name, size, years: PREVIEW_AGE_YEARS }),
            fetchCosts({ treeType: species.common_name }),
        ])
            .then(([g, c]) => {
                if (cancelled) return
                setGrowth(g)
                setCosts(Array.isArray(c) ? c[0] : c)
            })
            .catch(() => { if (!cancelled) setError("Couldn't load growth/cost data for this size.") })
            .finally(() => { if (!cancelled) setLoading(false) })
        return () => { cancelled = true }
    }, [species, size])

    if (!species) return null
    const priceRange = costs
        ? (costs.minimum_cost === costs.maximum_cost
            ? `$${costs.minimum_cost}`
            : `$${costs.minimum_cost}-$${costs.maximum_cost}`)
        : '—'
    console.log(priceRange);
    const canopyRange = growth
        ? `${growth.canopy_m2_min?.toFixed(0)}-${growth.canopy_m2_max?.toFixed(0)} m²`
        : '—'
    console.log(canopyRange);
    console.log(growth);
    const tree_size = growth
    ? {
        Small: { heightLabel: growth.height_m_min },
        Medium: { heightLabel: growth.height_m_median },
        Large: { heightLabel: growth.height_m_max },
    }
    : {};
    return (
        <div className={styles['panel-body']}>
            <img className={styles['detail-image']} src={species.image_url || undefined} alt={species.image_alt_text} />
            {/* <div className={styles['detail-image-placeholder']} aria-hidden="true" /> */}
            <h2 className={styles['panel-title']}>{species.common_name}</h2>
            <p className={styles['detail-latin']}>{species.scientific_name}</p>
            {species.description && (
                <p className={styles['detail-description']}>{species.description}</p>
            )}

            <div className={styles['fact-grid']}>
                <div className={styles['fact-tile']}>
                    <span className={styles['fact-label']}>Canopy at {PREVIEW_AGE_YEARS}y</span>
                    <strong className={styles['fact-value']}>{canopyRange}</strong>
                </div>
                <div className={styles['fact-tile']}>
                    <span className={styles['fact-label']}>Supply-only price</span>
                    <strong className={styles['fact-value']}>{priceRange}</strong>
                </div>
            </div>

            {loading && <p className={styles['detail-loading']}>Loading…</p>}
            {error && <p className={styles['detail-error']}>{error}</p>}
            {costs?.display_disclaimer && (
                <p className={styles['cost-disclaimer']}>{costs.display_disclaimer}</p>
            )}

            <div className={styles['section']}>
                <span>CHOOSE PLANTING SIZE</span>
                <div className={styles['price-container']}>
                    {Object.entries(tree_size).map(([label, { heightLabel }]) => (
                        <button
                            key={label}
                            type="button"
                            className={`${styles['size-option']} ${size === label ? styles['size-option--selected'] : ''}`}
                            onClick={() => onSizeChange(label)}
                        >
                            <span className={styles['size-radio']} />
                            <span className={styles['size-text']}>
                                <span className={styles['size-name']}>{label}</span>
                                <span className={styles['size-height']}>{heightLabel}m</span>
                            </span>
                        </button>
                    ))}
                </div>
            </div>
            <div className={styles['panel-actions']}>
                <div className={styles['panel-footer']}>
                    <button className={styles['back-button']} onClick={onBack}>Back</button>
                    <button
                        className={styles['apply-button']}
                        onClick={() => {onApply(growth); setCompareArray(prev => [...prev, species])}}
                        disabled={!size || !growth || applying || loading}
                    >
                        {applying ? 'Applying…' : `Apply ${size} to map`}
                    </button>
                </div>
                <button className={styles['exit-button']} onClick={onExit}>Exit</button>
            </div>
        </div>
    )
}