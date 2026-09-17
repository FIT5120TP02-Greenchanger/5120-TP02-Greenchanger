export const IMPACT_METRICS = [
    { key: 'projected_canopy_range_m2', label: 'Projected canopy at maturity', unit: 'm2_range' },
    { key: 'temperature_change_range_c', label: 'Land-surface temperature reduction', unit: 'temp_range' },
]

export function formatMetric(value, unit) {
    if (!value) return '—'
    if (unit === 'm2_range') {
        return `${value.minimum?.toFixed(1)}-${value.maximum?.toFixed(1)} m²`
    }
    if (unit === 'temp_range') {
        return `${value.minimum?.toFixed(1)}-${value.maximum?.toFixed(1)} °C`
    }
    return String(value)
}