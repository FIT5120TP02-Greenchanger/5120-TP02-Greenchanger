import CanopyPanel from "./CanopyPanel";
import HeatPanel from "./HeatPanel";
import styles from './Panel.module.css'

// TreeSimulator was removed from here — its size-picker was disconnected
// from actual simulation state (see PR discussion); real size selection
// now lives in TreePlacementPanel on PlantTreePage.
export default function SidePanel({stats, trees}) {
    return (
        <aside className={styles['side-panel']}>
            <CanopyPanel pct={trees.pct} nTrees={trees.nTrees} canopyM2={trees.canopyM2} viewM2={trees.viewM2} />
            <HeatPanel stats={stats} />
        </aside>
    )
}
