import { fmtArea } from "../utils/geo";
import styles from './Panel.module.css'

// export default function CanopyPanel({ pct, nTrees, canopyM2, viewM2 }) {
// simulatedCount added (2026-09-03): the numbers above include the trees the user placed
export default function CanopyPanel({ pct, nTrees, canopyM2, viewM2, simulatedCount }) {

    return (
        <div className={styles["canopy-panel"]}>
            <div className={styles['canopy-neighborhood']}>
                <span>CURRENT VIEWPORT</span>
                <div className={styles[`canopy-pct`]}>
                    <span>{pct.toFixed(1)}%</span>
                    <p>tree canopy</p>
                </div>
                <div className={styles["canopy-bar"]}>
                    <div
                        className={styles[`canopy-bar__fill`]}
                        style={{ width: `${Math.min(100, pct)}%` }}
                    />
                </div>
                <p className={styles["canopy-verdict"]}>
                    A live count of mapped tree points in view — not a neighbourhood classification.
                </p>
                {simulatedCount > 0 && (
                    <p className={styles["canopy-verdict"]}>
                        Includes {simulatedCount} simulated tree{simulatedCount === 1 ? "" : "s"} you placed.
                    </p>
                )}
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