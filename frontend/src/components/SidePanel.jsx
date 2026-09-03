import CanopyPanel from "./CanopyPanel";
import HeatPanel from "./HeatPanel";
// In-map planting (2026-09-03): the placement and scenario panels render inside the side panel
import TreePlacementPanel from "./TreePlacementPanel";
import ComparisonPanel from "./ComparisonPanel";
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
// export default function SidePanel({ stats, trees, simulating, isHomeSelected, onSimulate, onBackHome }) {
// placing / placement / scenario added (2026-09-03): in-map planting.
// scenarioOpen / simulatedCount / onResetScenario added (2026-09-03): while a scenario is open the
// panel shows only the planting or comparison panel (like the old PlantTreePage sidebar); after
// Done it is the normal panel again, with the placed trees counted in and a Reset button.
export default function SidePanel({
    stats, trees, simulating, isHomeSelected, onSimulate, onBackHome,
    placing, placement, scenario, scenarioOpen, simulatedCount, onResetScenario,
}) {
    if (scenarioOpen) {
        return (
            <aside className={styles['side-panel']}>
                {placing ? <TreePlacementPanel {...placement} /> : scenario ? <ComparisonPanel {...scenario} /> : null}
            </aside>
        );
    }
    return (
        <aside className={styles['side-panel']}>
            <CanopyPanel pct={trees.pct} nTrees={trees.nTrees} canopyM2={trees.canopyM2} viewM2={trees.viewM2} simulatedCount={simulatedCount} />
            <HeatPanel stats={stats} />

            <div className={styles['test-change']}>
                <span className={styles['test-change-label']}>TEST A CHANGE</span>
                {isHomeSelected ? (
                    <p>
                        {simulating
                            ? "Your lot is selected. Use the card on the map to plant a tree."
                            : "Your lot is pinned. Pick it, or any other lot on the street."}
                    </p>
                ) : (
                    <>
                        <p>{simulating ? "Another lot is selected." : "Another lot is picked."}</p>
                        <p>
                            <button type="button" className={styles['link-button']} onClick={onBackHome}>
                                Back to my home
                            </button>
                        </p>
                    </>
                )}
                {simulatedCount > 0 && (
                    <p>{simulatedCount} simulated tree{simulatedCount === 1 ? "" : "s"} on the map.</p>
                )}
                {/* The only way into simulate mode */}
                {!simulating && (
                    <button type="button" className={styles['simulate-button']} onClick={onSimulate}>
                        + Simulate a change
                    </button>
                )}
                {simulatedCount > 0 && (
                    <button type="button" className={styles['reset-trees-button']} onClick={onResetScenario}>
                        Reset simulated trees
                    </button>
                )}
            </div>
        </aside>
    )
}
