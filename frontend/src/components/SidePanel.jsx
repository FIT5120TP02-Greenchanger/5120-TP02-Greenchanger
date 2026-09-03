import CanopyPanel from "./CanopyPanel";
import HeatPanel from "./HeatPanel";
import styles from './Panel.module.css'

// TreeSimulator was removed from here — its size-picker was disconnected
// from actual simulation state (see PR discussion); real size selection
// now lives in TreePlacementPanel on PlantTreePage.
// export default function SidePanel({stats, trees}) {
    // return (
        // <aside className={styles['side-panel']}>
            // <CanopyPanel pct={trees.pct} nTrees={trees.nTrees} canopyM2={trees.canopyM2} viewM2={trees.viewM2} />
            // <HeatPanel stats={stats} />
        // </aside>
    // )
// }
// Arrive flow (2026-09-03): a "Test a change" section is the entry point into simulate mode
// (Figma "Test a change"). simulating / isHomeSelected / onSimulate / onBackHome come from MapView.
export default function SidePanel({ stats, trees, simulating, isHomeSelected, onSimulate, onBackHome }) {
    return (
        <aside className={styles['side-panel']}>
            <CanopyPanel pct={trees.pct} nTrees={trees.nTrees} canopyM2={trees.canopyM2} viewM2={trees.viewM2} />
            <HeatPanel stats={stats} />

            <div className={styles['test-change']}>
                <span className={styles['test-change-label']}>TEST A CHANGE</span>
                {!simulating && (
                    <>
                        <p>Your lot is pinned. Pick it, or any other lot on the street.</p>
                        <button type="button" className={styles['simulate-button']} onClick={onSimulate}>
                            + Simulate a change
                        </button>
                    </>
                )}
                {simulating && isHomeSelected && (
                    <p>Your lot is selected. Use the card on the map to plant a tree.</p>
                )}
                {simulating && !isHomeSelected && (
                    <>
                        <p>Another lot is selected.</p>
                        <button type="button" className={styles['link-button']} onClick={onBackHome}>
                            Back to my home
                        </button>
                    </>
                )}
            </div>
        </aside>
    )
}
