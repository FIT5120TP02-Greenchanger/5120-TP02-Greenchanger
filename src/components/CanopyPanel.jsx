import { fmtArea } from "../utils/geo";
import styles from './Panel.module.css'

// Thresholds from the data team's melbourne-terciles-v1 scheme —
// see the GreenChanger_data README. Update here if they publish v2.
const LOW_MAX = 28.8;
const MEDIUM_MAX = 72.53333;

export default function CanopyPanel({ pct, nTrees, canopyM2, viewM2 }) {
    const low = pct <= LOW_MAX;
    const medium = pct <= MEDIUM_MAX;
    const tone = low ? "rust" : "green";

    const verdict = low
        ? `Below the neighbourhood low threshold of ${LOW_MAX}%.`
        : medium
        ? `Above the low threshold, within the medium band (up to ${MEDIUM_MAX.toFixed(1)}%).`
        : "This view is in the high band for neighbourhood canopy.";

    return (
        <div className={styles["canopy-panel"]}>
            <div className={styles['canopy-neighborhood']}>
                <span>THIS NEIGHBORHOOD</span>
                <div className={styles[`canopy-pct`]}>
                    <span>{pct.toFixed(1)}%</span>
                    <p>tree canopy</p>
                </div>
                <div className={styles["canopy-bar"]}>
                    <div
                        className={styles[`canopy-bar__fill`]}
                        style={{ width: `${Math.min(100, (pct / MEDIUM_MAX) * 100)}%` }}
                    />
                    <div className={styles['canopy-scale']}>
                        <p>0%</p>
                        <p>{LOW_MAX}%</p>
                        <p>{MEDIUM_MAX.toFixed(1)}%</p>
                    </div>
                </div>
                <p className={styles["canopy-verdict"]}>{verdict}</p>
            </div>
            <div className={styles["canopy-view"]}>
                <span>WHAT IS HERE NOW</span>
                <dl className={styles["canopy-stats"]}>
                    <dt>Trees</dt>
                    <dd>{nTrees.toLocaleString()}</dd>
                    <dt>Canopy area</dt>
                    <dd>{fmtArea(canopyM2)}</dd>
                    <dt>View area</dt>
                    <dd>{fmtArea(viewM2)}</dd>
                </dl>
            </div>
        </div>
    );
}