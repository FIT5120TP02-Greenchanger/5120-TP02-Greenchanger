import styles from '../TreePlantingFlow.module.css'
import card_styles from '../../Panel.module.css'

export default function Impact({ scenario, onViewGuidance, onBack, onCompare, onExit }) {
    if (!scenario) return null
    const { species, size, impact, growth } = scenario
    const temp_change = `${impact.temperature_change_range_c.minimum}-${impact.temperature_change_range_c.maximum}`
    const canopy_change = `${growth.canopy_m2_min}-${growth.canopy_m2_max}`
    const shade_change = `${growth.crown_width_m_min}-${growth.crown_width_m_max}`
    return (
        <>
            <div className={styles['panel-body']}>
                <span className={styles['user-note']}>Impact of planting a tree</span>
                <h2 className={styles['panel-title']}>{species?.common_name} on your lot</h2>
                <p className={styles['subtitle']}>
                    {size} size placed at your simulated position, at {impact?.maturity_horizon_years} years.
                </p>
                <p className={styles['subtitle']}>
                    Figures are not guarantees.
                </p>

                <div className={styles['section']}>
                    <span className={styles['user-note']}>INDICATIVE IMPACT</span>
                    <span className={styles['impact-value']}>+{canopy_change} m²</span>
                    <p className={styles['impact-caption']}>additional canopy at maturity</p>
                </div>
                <div className={card_styles['scenario-card']}>
                    <span className={card_styles['scenario-card-label']}>TEMPERATURE CHANGE</span>
                    <div className={card_styles['scenario-card-pct']}>+{temp_change}°C</div>
                </div>

                <div className={`${card_styles['scenario-card']} ${card_styles['scenario-card--simulated']}`}>
                    <span className={card_styles['scenario-card-label']}>
                        SHADE CHANGE
                    </span>
                    <div className={card_styles['scenario-card-pct']}>{shade_change} m² shade</div>
                </div>
                {/* {impact?.calculation_assumption && (
                    <p className={styles['impact-disclaimer']}>{impact.calculation_assumption}</p>
                )} */}

                <div className={styles['section']}>
                    <div className={styles['metric-list']}>
                        <span className={styles['user-note']}>INDICATIVE CHARACTERISTICS</span>
                        <p className={styles['map-key-item']}>Dashed ring = indicative mature canopy</p>
                        <p className={styles['map-key-item']}>Soft grey shape = example 3 pm shade</p>
                    </div>
                </div>

                <div className={styles['map-key']}>
                    <p className={styles['map-key-title']}>Map preview</p>
                    <p className={styles['map-key-item']}>Dashed ring = indicative mature canopy</p>
                    <p className={styles['map-key-item']}>Soft grey shape = example 3 pm shade</p>
                </div>
            </div>

            <div className={styles['panel-actions']}>
                <div className={styles['panel-footer']}>
                    <button type="button" className={styles['compare-button']} onClick={onCompare}>
                        Compare with another tree
                    </button>
                    <button type="button" className={styles['back-button']} onClick={onBack}>
                        Change species
                    </button>

                </div>
                <div className={styles['panel-footer']}>
                    <button type="button" className={styles['exit-button']} onClick={onExit}>Exit</button>
                    <button type="button" className={styles['guidance-button']} onClick={onViewGuidance}>
                        View guidance
                    </button>
                </div>
            </div>
        </>
    )
}
