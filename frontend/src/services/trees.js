export const PREVIEW_AGE_YEARS = 20;

async function getJson(path, params = {}) {
    const query = new URLSearchParams(
        Object.entries(params).filter(([, v]) => v != null && v !== "")
    );
    const url = query.toString() ? `${path}?${query}` : path;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${path} failed (${res.status})`);
    return res.json();
}

// Returns the top 10 most common tree species in Melbourne (by real planting records), each flagged with whether it has growth-model data.
export function fetchSpecies(address) {
    return getJson("/api/trees/species", { address });
}

// Canopy / crown width / height / DBH ranges for a species at a given age.
export function fetchGrowth({ species, size, years = PREVIEW_AGE_YEARS }) {
    return getJson("/api/trees/growth", { species, size, years });
}

// Real supplier pricing. Both filters optional.
export function fetchCosts({ optionCode, treeType } = {}) {
    return getJson("/api/trees/costs", { option_code: optionCode, tree_type: treeType });
}

// Scenario impact. Passing species+size makes the backend use the real growth model.
export async function simulateScenario({ inputs }) {
    const res = await fetch("/api/scenario/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action_type: "tree", inputs }),
    });
    if (!res.ok) throw new Error(`simulate failed (${res.status})`);
    return res.json();
}