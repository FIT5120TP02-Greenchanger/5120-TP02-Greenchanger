import { useEffect, useState } from "react";
import { fetchSpecies } from "../services/trees";

export const LOAD_ERROR="Could not load tree species.";

export function useSpecies(activeAddress, setSpeciesCatalogue) {
    const [error, setError] = useState(null)
    useEffect(() => {
        if (!activeAddress) { setSpeciesCatalogue([]); return; }
        let cancelled = false;

        fetchSpecies(activeAddress)
            .then((data) => {
                if (!cancelled) {setSpeciesCatalogue((data?.species || []).filter((s) => s.has_growth_model)); setError(null);}
            })
            .catch(() => { if (!cancelled) { setSpeciesCatalogue([]); setError(activeAddress); } });
        return () => { cancelled = true; };
    }, [activeAddress, setSpeciesCatalogue]);
    return activeAddress && failedAddress === activeAddress ? LOAD_ERROR : null;
}