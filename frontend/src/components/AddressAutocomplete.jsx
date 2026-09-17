import { useState, useEffect, useRef, useCallback } from 'react';
import { searchAddresses } from '../services/vicmap';
import styles from './AddressAutocomplete.module.css';

// Deliberately NOT Mapbox's SearchBox. Whatever string the user picks here
// is the backend's own full_address — guaranteed to match
// /api/properties/baseline exactly, since it came from the same table.
// Mapbox's geocoded strings don't reliably match (different casing,
// abbreviations, house-number placement), which is what caused baseline
// lookups to 404 despite looking like the right address to a human.
export default function AddressAutocomplete({ value, onChange, onSelect, placeholder }) {
    const [suggestions, setSuggestions] = useState([]);
    const [open, setOpen] = useState(false);
    const [loading, setLoading] = useState(false);

    const debounceRef = useRef(null);
    const searchIdRef = useRef(0); // to ignore out-of-order responses

    const runSearch = useCallback((query) => {
        clearTimeout(debounceRef.current);
        const query_trimmed = query.trim();
        if (query_trimmed.length < 3) {
            setSuggestions([]);
            setOpen(false);
            setLoading(false);
            return;
        }
        
        debounceRef.current = setTimeout(async () => {
            const searchId = ++searchIdRef.current;

            setLoading(true);
            setOpen(true);
            try {
                const results = await searchAddresses(query_trimmed);
                if (searchId !== searchIdRef.current) return; // ignore out-of-order responses
                setSuggestions(results);
            } catch(error) {
                console.error('Error searching addresses:', error);
                if (searchId === searchIdRef.current) {
                    setSuggestions([]);
                }
            } finally {
                if (searchId === searchIdRef.current) {
                    setLoading(false);
                }
            }
        }, 150);
    }, []);

    const handleInputChange = (e) => {
        const next = e.target.value;
        onChange(next);
        runSearch(next);
    };

    const handleSelect = (suggestion) => {
        onChange(suggestion.full_address);
        setSuggestions([]);
        setOpen(false);
        onSelect(suggestion);
    };

    useEffect(() => {
        return () => {
            clearTimeout(debounceRef.current);
        };
    }, []);

    return (
        <div className={styles['autocomplete']}>
            <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 15 15" fill="none">
            <circle cx="7.5" cy="7.5" r="6.65" stroke="#7C858B" stroke-width="1.7"/>
            </svg>
            <input
                className={styles['autocomplete-input']}
                value={value}
                onChange={handleInputChange}
                onFocus={() => suggestions.length && setOpen(true)}
                onBlur={() => setTimeout(() => setOpen(false), 150)} // let click land first
                placeholder={placeholder}
            />
            {open && (
                <ul className={styles['autocomplete-list']}>
                    {loading && <li className={styles['autocomplete-status']}>Searching…</li>}
                    {!loading && suggestions.length === 0 && (
                        <li className={styles['autocomplete-status']}>No matches</li>
                    )}
                    {suggestions.map((s) => (
                        <li key={s.address_id}>
                            <button
                                type="button"
                                className={styles['autocomplete-item']}
                                onMouseDown={(e) => e.preventDefault()}
                                onClick={() => handleSelect(s)}
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" width="19" height="28" viewBox="0 0 19 28" fill="none">
                                <path d="M9.5 26.5C6.9 20.9 0.5 15.9 0.5 9.5C0.5 4.5 4.5 0.5 9.5 0.5C14.5 0.5 18.5 4.5 18.5 9.5C18.5 15.9 12.1 20.9 9.5 26.5Z" fill="#2F7D5A" stroke="black"/>
                                    <circle cx="12" cy="9" r="2.5" />
                                </svg>
                                {s.full_address}
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}