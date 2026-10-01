import { useEffect, useState } from "react";
import { fetchSpecies } from "../services/trees";

export const LOAD_ERROR="Could not load tree species.";

export function useSpecies(activeAddress, setSpeciesCatalogue) {
    const [error, setError] = useState(null)
    useEffect(() => {
        if (!activeAddress) { setSpeciesCatalogue([]); setError(null); return; }
        let cancelled = false;
        setError(null);

        fetchSpecies(activeAddress)
            .then((data) => {
                if (!cancelled) setSpeciesCatalogue((data?.species || []).filter((s) => s.has_growth_model));
            })
            .catch((err) => { if (!cancelled) { setSpeciesCatalogue([]); setError("Could not load tree species."); } });
        return () => { cancelled = true; };
    }, [activeAddress, setSpeciesCatalogue]);
    return error;
}