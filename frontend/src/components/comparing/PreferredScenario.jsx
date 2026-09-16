import styles from './TreeChoosing.module.css'
import list_styles from '../planning/TreePlantingFlow.module.css'
import {
    canopyAddedRange, canopyCoverAfter, spaceNeededM2,
    shadeLevel, coolingLevel, priceRange, formatRange, formatPrice, levelDiffLabel,
} from './scenarioMetrics'

export default function PreferredScenario({
    compareArray = [],
    rows,
    preferredKey,
    canopyM2,
    viewM2,
    onChangePreference,
    onRemovePreference,
    onBack,
    onViewGuidance,
}) {
    const preferredIndex = compareArray.findIndex((s) => s.species_key === preferredKey)
    const preferred = rows[preferredKey]
    if (!preferred) return null // shouldn't happen — guard in case preferredKey is stale

    // Compare against the first other scenario in the list (screenshot only ever shows one).
    const otherIndex = compareArray.findIndex((s) => s.species_key !== preferredKey)
    const other = otherIndex >= 0 ? rows[compareArray[otherIndex].species_key] : null

    const label = String.fromCharCode(65 + preferredIndex)
    const price = formatPrice(priceRange(preferred))
    const coverAfter = canopyCoverAfter(preferred, canopyM2, viewM2)

    return (
        <div className={styles['compare-panel']}>
            <div className={styles['compare-header']}>
                <h1 className={styles['panel-title']}>Your preferred scenario</h1>
                <p className={styles['compare-subtitle']}>
                    Saved as your choice for this lot. You can change it any time; it is not a recommendation.
                </p>
            </div>

            <div className={styles['compare-species-card']}>
                <div className={styles['compare-species-heading']}>
                    <span className={styles['compare-species-badge']}>{label}</span>
                    <div>
                        <h2>{preferred.species.common_name}</h2>
                        <p>{preferred.size} · {price} supply-only</p>
                    </div>
                    <span className={styles['preferred-badge']}>PREFERRED</span>
                </div>

                <div className={styles['compare-table']}>
                    <SingleRow label="Added canopy at maturity" value={`+${formatRange(canopyAddedRange(preferred), ' m²')}`} />
                    <SingleRow label="Canopy cover after planting" value={coverAfter ? `${coverAfter.pct.toFixed(1)}%` : '—'} />
                    <SingleRow label="Shade potential" value={shadeLevel(preferred) ?? '—'} />
                    <SingleRow label="Cooling potential" value={coolingLevel(preferred) ?? '—'} />
                    <SingleRow label="Space needed on lot" value={spaceNeededM2(preferred) != null ? `${spaceNeededM2(preferred).toFixed(0)} m²` : '—'} />
                </div>
            </div>

            {other && (
                <div className={styles['compare-table']}>
                    <div className={styles['compare-section-label']}>
                        COMPARED WITH SCENARIO {String.fromCharCode(65 + otherIndex)} — {other.species.common_name}
                    </div>
                    <SingleRow label="Canopy at maturity" value={canopyDiffLabel(preferred, other)} />
                    <SingleRow label="Shade and cooling" value={levelDiffLabel(shadeLevel(preferred), shadeLevel(other))} />
                    <SingleRow label="Space needed on lot" value={spaceDiffLabel(preferred, other)} />
                    <SingleRow label="Supply-only price" value={priceDiffLabel(preferred, other)} />
                </div>
            )}

            <div style={{ display: 'flex', gap: 8 }}>
                <button type="button" className={styles['link-button'] || undefined} onClick={onChangePreference}>Change preference</button>
                <button type="button" className={styles['link-button'] || undefined} onClick={onRemovePreference}>Remove preference</button>
            </div>

            <div className={list_styles['panel-actions']}>
                <div className={list_styles['panel-footer']}>
                    <button type="button" className={list_styles['back-button']} onClick={onBack}>Back to comparison</button>
                    <button type="button" className={styles['guidance-button']} onClick={onViewGuidance}>View planting guidance</button>
                </div>
            </div>
        </div>
    )
}

function SingleRow({ label, value }) {
    return (
        <div className={styles['compare-row']}>
            <div className={styles['compare-row-label']}>{label}</div>
            <div className={styles['compare-row-value']}>{value}</div>
        </div>
    )
}

function canopyDiffLabel(preferred, other) {
    const p = canopyAddedRange(preferred), o = canopyAddedRange(other)
    if (!p || !o) return '—'
    const diff = (p.min + p.max) / 2 - (o.min + o.max) / 2
    return diff === 0 ? 'Same' : `${diff > 0 ? '+' : ''}${diff.toFixed(0)} m² ${diff > 0 ? 'more' : 'less'}`
}
function spaceDiffLabel(preferred, other) {
    const p = spaceNeededM2(preferred), o = spaceNeededM2(other)
    if (p == null || o == null) return '—'
    const diff = p - o
    return diff === 0 ? 'Same' : `${diff > 0 ? '+' : ''}${diff.toFixed(0)} m² ${diff > 0 ? 'more' : 'less'}`
}
function priceDiffLabel(preferred, other) {
    const p = priceRange(preferred), o = priceRange(other)
    if (!p || !o) return '—'
    const diff = p.min - o.min // using min end of range as the headline price, matching the card display
    return diff === 0 ? 'Same' : `${diff > 0 ? '+' : '-'}$${Math.abs(diff)}`
}