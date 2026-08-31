import { useState } from 'react';
import styles from './Panel.module.css'

const options = [
    {
        id: 1,
        Title: 'Small',
        Height: '5m',
        Price: '$100'
    },
    {
        id: 2,
        Title: 'Medium',
        Height: '8m',
        Price: '$500'
    },
    {
        id: 3,
        Title: 'Large',
        Height: '12m',
        Price: '$1000'
    }
]

export default function TreeSimulator() {
    const [selectedOption, setSelectedOption] = useState(null);
    return (
        <div className={styles['simulator-container']}>
            <span>TEST A CHANGE</span>
            <span>Your lot is pinned. Pick it, or any other lot on the street.</span>
            <button className={styles["plant-button"]}>+ Simulate Change</button>
        </div>
    )
}