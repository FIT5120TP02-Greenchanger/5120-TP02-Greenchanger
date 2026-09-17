import { useEffect, useRef } from 'react'
import styles from './TreeChoosing.module.css'
import list_styles from '../planning/TreePlantingFlow.module.css'
import {
    canopyAddedRange, canopyCoverAfter, matureCanopyWidthRange,
    spaceNeededM2, shadeLevel, coolingLevel, priceRange, formatRange, formatPrice,
} from './scenarioMetrics'

const SIZES = ['Small', 'Medium', 'Large']
const DEFAULT_ROW_SIZE = 'Medium'

export default function TreeCompare({ compareArray = [], appliedScenario, rows, onRowsChange, fetchScenarioFor, canopyM2, viewM2, preferredKey, onChoosePreferred, onBack }) {
    // Kick off a fetch for any species in compareArray that doesn't have row data yet.
    // A ref (not `rows` itself) is used to check existence so this effect doesn't
    // re-fire every time onRowsChange updates state.
    const rowsRef = useRef(rows)
    useEffect(() => { rowsRef.current = rows }, [rows])

    useEffect(() => {
        let cancelled = false

        compareArray.forEach((s) => {
            if (rowsRef.current[s.species_key]) return

            // The species already applied to the map: reuse the growth/costs/impact
            // SpeciesDetail already fetched instead of re-fetching it here.
            if (appliedScenario && s.species_key === appliedScenario.species.species_key) {
                onRowsChange((prev) => ({
                    ...prev,
                    [s.species_key]: {
                        species: s, size: appliedScenario.size,
                        growth: appliedScenario.growth, costs: appliedScenario.costs, impact: appliedScenario.impact,
                        loading: false, error: null,
                    },
                }))
                return
            }

            onRowsChange((prev) => ({ ...prev, [s.species_key]: { species: s, size: DEFAULT_ROW_SIZE, loading: true, error: null } }))
            fetchScenarioFor(s, DEFAULT_ROW_SIZE)
                .then((data) => { if (!cancelled) onRowsChange((prev) => ({ ...prev, [s.species_key]: { ...data, loading: false, error: null } })) })
                .catch(() => { if (!cancelled) onRowsChange((prev) => ({ ...prev, [s.species_key]: { ...prev[s.species_key], loading: false, error: "Could not load this species." } })) })
        })

        // Drop rows for species no longer selected (e.g. user went back and unchecked one).
        onRowsChange((prev) => {
            const keys = new Set(compareArray.map((s) => s.species_key))
            const next = {}
            for (const key of Object.keys(prev)) if (keys.has(key)) next[key] = prev[key]
            return next
        })

        return () => { cancelled = true }
    }, [compareArray, appliedScenario, fetchScenarioFor, onRowsChange])

    function handleSizeChange(key, newSize) {
        const row = rows[key]
        if (!row || row.size === newSize) return
        onRowsChange((prev) => ({ ...prev, [key]: { ...prev[key], size: newSize, loading: true, error: null } }))
        fetchScenarioFor(row.species, newSize)
            .then((data) => onRowsChange((prev) => ({ ...prev, [key]: { ...data, loading: false, error: null } })))
            .catch(() => onRowsChange((prev) => ({ ...prev, [key]: { ...prev[key], loading: false, error: "Could not load this size." } })))
    }

    const orderedRows = compareArray.map((s) => rows[s.species_key]).filter(Boolean)

    return (
        <div className={styles['compare-panel']} style={{
            '--compare-column-count': compareArray.length,
        }}>
            <div className={styles['compare-header']}>
                <h1 className={styles['panel-title']}>Compare scenarios</h1>
                <p className={styles['compare-subtitle']}>
                    Same lot, same indicators, shown at maturity. Values are indicative.
                </p>
            </div>

            <div className={styles['compare-species-grid']}>
                <div className={styles['compare-label-column']} />
                    {compareArray.map((s, index) => {
                        const row = rows[s.species_key]
                        const label = String.fromCharCode(65 + index)

                        const price = row
                            ? formatPrice(priceRange(row))
                            : null

                        return (
                            <div
                                key={s.species_key}
                                className={styles['compare-species-card']}
                            >
                                <div className={styles['compare-species-heading']}>
                                    <span
                                        className={
                                            styles['compare-species-badge']
                                        }
                                    >
                                        {label}
                                    </span>

                                    <div>
                                        <h2>
                                            {s.common_name || 'Unknown species'}
                                        </h2>

                                        <p>
                                            {row?.loading
                                                ? 'Loading data...'
                                                : row?.size
                                                ? `${row.size} · ${price} supply-only`
                                                : 'Data unavailable'}
                                        </p>
                                    </div>
                                </div>

                                <div className={styles['compare-size-toggle']}>
                                    {SIZES.map((size) => (
                                        <button
                                            key={size}
                                            type="button"
                                            aria-pressed={row?.size === size}
                                            disabled={!row || row.loading}
                                            onClick={() =>
                                                handleSizeChange(
                                                    s.species_key,
                                                    size
                                                )
                                            }
                                        >
                                            {size[0]}
                                        </button>
                                    ))}
                                </div>

                                <button
                                    type="button"
                                    className={
                                        styles['compare-preferred-button']
                                    }
                                    disabled={!row || row.loading}
                                    aria-pressed={
                                        preferredKey === s.species_key
                                    }
                                    onClick={() =>
                                        onChoosePreferred(s.species_key)
                                    }
                                >
                                    {preferredKey === s.species_key
                                        ? 'Preferred'
                                        : 'Choose as preferred'}
                                </button>
                            </div>
                        )
                    })}

                    <div className={styles['compare-section-label']}>CANOPY</div>
                    <CompareRow label="Added canopy at maturity" rows={orderedRows} render={(r) => `+${formatRange(canopyAddedRange(r), ' m²')}`} />
                    <CompareRow label="Canopy cover after planting" rows={orderedRows} render={(r) => {
                        const c = canopyCoverAfter(r, canopyM2, viewM2)
                        return c ? `${c.pct.toFixed(1)}%` : '—'
                    }} />

                    <div className={styles['compare-section-label']}>SHADE & COOLING</div>
                    <CompareRow label="Shade potential" rows={orderedRows} render={(r) => shadeLevel(r) ?? '—'} />
                    <CompareRow label="Cooling potential" rows={orderedRows} render={(r) => coolingLevel(r) ?? '—'} />

                    <div className={styles['compare-section-label']}>SPACE</div>
                    <CompareRow label="Mature canopy width" rows={orderedRows} render={(r) => formatRange(matureCanopyWidthRange(r), ' m')} />
                    <CompareRow label="Space needed on lot" rows={orderedRows} render={(r) => {
                        const m2 = spaceNeededM2(r)
                        return m2 != null ? `${m2.toFixed(0)} m²` : '—'
                    }} />

                    <div className={styles['compare-section-label']}>COST</div>
                    <CompareRow label="Supply-only price" rows={orderedRows} render={(r) => formatPrice(priceRange(r))} />
                </div>

                <p className={styles['compare-note']}>
                    Results are indicative and are not guaranteed outcomes.
                </p>

                <div className={list_styles['panel-actions']}>
                    <div className={list_styles['panel-footer']}>
                        <button type="button" className={list_styles['back-button']} onClick={onBack}>Edit selection</button>
                    </div>
                </div>
        </div>
    )
}

function CompareRow({ label, rows, render }) {
    return (
        <>
            <div className={styles['compare-row-label']}>{label}</div>
            {rows.map((r) => (
                <div key={r.species.species_key} className={styles['compare-row-value']}>
                    {r.loading ? '…' : (r.error ? '—' : render(r))}
                </div>
            ))}
        </>
    )
}