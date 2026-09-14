import styles from '../TreePlantingFlow.module.css';
export default function Benefits({ scenario, onBack, onViewGuidance, onExit }) {
    return (
        <div className={styles['benefits']}>
            <span>BENEFITS OF PLANTING A TREE</span>
            <p>Planting a {scenario?.species?.commonName} ({scenario?.size}) on your lot would provide the following benefits:</p>
            <ul>
                <li>Carbon sequestration: {scenario?.impact?.carbonSequestration.toFixed(2)} kg CO₂ per year</li>
                <li>Stormwater interception: {scenario?.impact?.stormwaterInterception.toFixed(2)} m³ per year</li>
                <li>Energy savings: {scenario?.impact?.energySavings.toFixed(2)} kWh per year</li>
                <li>Air quality improvement: {scenario?.impact?.airQualityImprovement.toFixed(2)} kg PM10 per year</li>
            </ul>
            <button className={styles['back-button']} onClick={ onBack }>Back</button>
            <button className={styles['guidance-button']} onClick={ onViewGuidance }>View guidance</button>
            <button className={styles['exit-button']} onClick={ onExit }>Exit</button>
        </div>
    );
}