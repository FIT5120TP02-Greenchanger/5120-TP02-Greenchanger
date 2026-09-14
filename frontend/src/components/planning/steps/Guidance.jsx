import styles from '../TreePlantingFlow.module.css';
export default function Guidance({ onBack, onStartAgain, onExit }) {
    return (
        <div className={styles['guidance']}>
            <span>GUIDANCE FOR PLANTING A TREE</span>
            <p>Planting a tree is a long-term commitment. Here are some tips to help you get started:</p>
            <ul>
                <li>Choose the right species for your location and climate.</li>
                <li>Consider the mature size of the tree and its impact on your property.</li>
                <li>Plant the tree in a suitable location with enough space for growth.</li>
                <li>Water and care for the tree regularly, especially during the first few years.</li>
                <li>Prune and maintain the tree as needed to ensure healthy growth.</li>
            </ul>
            <button className={styles['back-button']} onClick={onBack}>Back</button>
            <button className={styles['start-again-button']} onClick={onStartAgain}>Start Again</button>
            <button className={styles['exit-button']} onClick={onExit}>Exit</button>
        </div>
    );
}