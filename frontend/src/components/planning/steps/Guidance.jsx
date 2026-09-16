import styles from '../TreePlantingFlow.module.css'

const GUIDANCE_STEPS = [
    ['Check space', 'Allow for mature canopy, roots and distance from structures.'],
    ['Check local conditions', 'Consider soil, sun, water and Melbourne climate exposure.'],
    ['Check animals and safety', 'Protect young trees; consider pets, wildlife and browsing damage.'],
    ['Water and establish', 'Water regularly through the first two or three summers.'],
    ['Confirm local guidance', 'Check council species lists, permits and underground services.'],
]

export default function Guidance({ onBack, onStartAgain, onExit }) {
    return (
        <>
            <div className={styles['panel-body']}>
                <span className={styles['eyebrow']}>Guidance for planting a tree</span>
                <h2 className={styles['panel-title']}>General planting guidance</h2>
                <p className={styles['subtitle']}>
                    Use these prompts before making a real-world planting decision.
                </p>

                <ol className={styles['guidance-steps']}>
                    {GUIDANCE_STEPS.map(([title, text], i) => (
                        <li key={title} className={styles['guidance-step']}>
                            <span className={styles['step-number']}>{String(i + 1).padStart(2, '0')}</span>
                            <div className={styles['step-text']}>
                                <strong className={styles['step-title']}>{title}</strong>
                                <p className={styles['step-description']}>{text}</p>
                            </div>
                        </li>
                    ))}
                </ol>

                <div className={styles['limitation']}>
                    <p className={styles['limitation-title']}>Important limitation</p>
                    <p className={styles['limitation-text']}>
                        This prototype supports exploration only. It is not arboricultural or legal advice.
                    </p>
                </div>
            </div>

            <div className={styles['panel-actions']}>
                <div className={styles['panel-footer']}>
                    <button type="button" className={styles['back-button']} onClick={onBack}>
                        Back
                    </button>
                    <button type="button" className={styles['start-again-button']} onClick={onStartAgain}>
                        Start again
                    </button>
                </div>
            </div>
        </>
    )
}