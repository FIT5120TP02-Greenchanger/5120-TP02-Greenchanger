import { useState, useEffect } from 'react'
import styles from '../TreePlantingFlow.module.css'
import { fetchGrowth, fetchCosts, PREVIEW_AGE_YEARS } from '../../../services/trees'

const SIZE_OPTIONS = ['Small', 'Medium', 'Large']
const EMPTY_GROWTH = {
    Small: null,
    Medium: null,
    Large: null,
}
export default function SpeciesDetail({ species, size, onSizeChange, setCompareArray, onApply, applying, onBack, onExit }) {
    const [growthBySize, setGrowthBySize] = useState(EMPTY_GROWTH)
    const [costs, setCosts] = useState(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)

    useEffect(() => {
        if (!species) return

        let cancelled = false
        // Reset before fetching so a size flip mid-flight can't show stale data
        // this is the "ignore" idiom from the React docs' fetch-in-effect guide
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setLoading(true)
        setGrowthBySize({
            Small: null,
            Medium: null,
            Large: null,
        })
        setCosts(null)
        setError(null)
        async function loadData() {
            try {
                const [smallGrowth, mediumGrowth, largeGrowth, costsRaw] =
                    await Promise.all([
                        fetchGrowth({
                            species: species.scientific_name,
                            size: 'Small',
                            years: PREVIEW_AGE_YEARS,
                        }),
                        fetchGrowth({
                            species: species.scientific_name,
                            size: 'Medium',
                            years: PREVIEW_AGE_YEARS,
                        }),
                        fetchGrowth({
                            species: species.scientific_name,
                            size: 'Large',
                            years: PREVIEW_AGE_YEARS,
                        }),
                        fetchCosts({
                            treeType: species.common_name,
                        }),
                    ])

                if (cancelled) return

                setGrowthBySize({
                    Small: smallGrowth,
                    Medium: mediumGrowth,
                    Large: largeGrowth,
                })

                setCosts(Array.isArray(costsRaw) ? costsRaw[0] : costsRaw)
            } catch {
                if (!cancelled) {
                    setError("Couldn't load growth/cost data.")
                }
            } finally {
                if (!cancelled) {
                    setLoading(false)
                }
            }
        }
        loadData()
        return () => { cancelled = true }
    }, [species])

    if (!species) return null

    const growth = growthBySize[size]

    const priceRange = costs
        ? (
            costs.minimum_cost === costs.maximum_cost
                ? `$${costs.minimum_cost}`
                : `$${costs.minimum_cost}-$${costs.maximum_cost}`
        )
        : '—'

    const canopyRange = growth
        ? `${growth.canopy_m2_min?.toFixed(0)}-${growth.canopy_m2_max?.toFixed(0)} m²`
        : '—'
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
                    {SIZE_OPTIONS.map((label) => {
                        const sizeGrowth = growthBySize[label]

                        const heightRange = sizeGrowth
                            ? `${sizeGrowth.height_m_min?.toFixed(1)}m - ${sizeGrowth.height_m_max?.toFixed(1)}m`
                            : 'Loading…'

                        return (
                            <button
                                key={label}
                                type="button"
                                className={`${styles['size-option']} ${
                                    size === label
                                        ? styles['size-option--selected']
                                        : ''
                                }`}
                                onClick={() => onSizeChange(label)}
                            >
                                <span className={styles['size-radio']} />

                                <span className={styles['size-text']}>
                                    <span className={styles['size-name']}>
                                        {label}
                                    </span>

                                    <span className={styles['size-height']}>
                                        {heightRange}
                                    </span>
                                </span>
                            </button>
                        )
                    })}
                </div>
            </div>
            <div className={styles['panel-actions']}>
                <div className={styles['panel-footer']}>
                    <button className={styles['back-button']} onClick={onBack}>Back</button>
                    <button
                        className={styles['apply-button']}
                        onClick={() => { onApply(growth, costs); setCompareArray(prev => [...prev, species]) }}
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