export default function PlantModeChooser({ onQuickSimulation, onExploreSpecies, onCancel }) {
    return (
        <div>
            <a href="#" onClick={(e) => { e.preventDefault(); onCancel(); }}>Plant a tree</a>
            <h3>How would you like to explore?</h3>
            <p>Try a quick canopy simulation, or choose a tree species.</p>

            <button onClick={onQuickSimulation}>
                <strong>Quick simulation</strong>
                <p>Choose a canopy size and preview one tree's impact.</p>
            </button>

            <button onClick={onExploreSpecies}>
                <strong>Explore tree species</strong>
                <p>Choose a species, view details, and personalise your tree.</p>
            </button>

            <p>Planning preview only. Prices are not yet verified.</p>
            <button onClick={onCancel}>Cancel</button>
        </div>
    );
}