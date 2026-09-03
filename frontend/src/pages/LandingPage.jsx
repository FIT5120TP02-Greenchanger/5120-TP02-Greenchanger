import styles from './LandingPage.module.css';
// import { SearchBox } from '@mapbox/search-js-react';
import AddressAutocomplete from '../components/AddressAutocomplete';
import { useState } from 'react';

// Landing v2 (2026-09-03): the colour legend was removed from the design, so `colors` is unused.
// const colors = [
    // {id: 1, color: "#E9E2D0"},
    // {id: 2, color: "#DFDCC4"},
    // {id: 3, color: "#CFD6B4"},
    // {id: 4, color: "#B7CB9E"},
    // {id: 5, color: "#95B884"},
    // {id: 6, color: "#6DA269"},
    // {id: 7, color: "#3F7A52"}
// ];

// Landing v2: chevron drawn between the three "how it works" steps.
// Colour comes from the .step-arrow CSS rule via currentColor.
const stepArrow = (
    <svg className={styles["step-arrow"]} viewBox="0 0 7 12" fill="none" aria-hidden="true">
        <path d="M0.8 0.8L5.8 5.8L0.8 10.8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
);


export default function LandingPage({onNavigate, selectedLocation, setSelectedLocation}) {
    const [addressInput, setAddressInput] = useState(selectedLocation?.address || "");
    const [error, setError] = useState("");
    
    const handleSubmit = (e) => {
        e.preventDefault();
        if (!selectedLocation?.address?.trim()) {
            setError("Pick an address from the dropdown to continue.");
            return;
        }
        onNavigate('map');
    }

    const handleAddressSelect = (location) => {
        // const feature = location.features?.[0];
        // if (!feature) return;
        // const coordinates = feature.geometry?.coordinates;
        // const label = feature.properties?.full_address || feature.properties?.name || addressInput;

        setSelectedLocation(
            {
                address: location.full_address,
                addressId: location.address_id
            }
        );
        setAddressInput(location.full_address);
    };
    const handleAddressChange = (location) => {
        setSelectedLocation(null);
        setAddressInput(location);
    };

    // Landing v2 (2026-09-03): original markup kept below for reference; new markup follows it.
    // return (
        // <div className={styles["landing-container"]}>
            // <div className={styles["landing-page-brand"]}>
                // <div className={styles["landing-page-mark"]}></div>
                // <p>Green Changer</p>
            // </div>

            // <div className={styles["hero-card"]}>
                // <h1 className={styles["landing-title"]}>Some Melbourne streets have four times the tree canopy of others</h1>
                // <p className={styles["landing-description"]}>
                    // Find out where you sits - and see what one more tree would actually change.
                // </p>
                // <form className={styles["address-search-container"]} onSubmit={handleSubmit}>
                        // {/* <SearchBox
                            // accessToken={import.meta.env.VITE_MAPBOX_ACCESS_TOKEN}
                            // onRetrieve={handleAddressSelect}
                            // onChange={handleAddressChange}
                            // value={addressInput}
                            // placeholder="Search for an address"
                            // options={{
                                // country: 'AU',
                                // language: 'en',
                                // types: 'address',
                                // bbox: [
                                    // 144.4,
                                    // -38.3,
                                    // 145.5,
                                    // -37.4
                                // ]
                            // }}
                            // theme={{
                                // variables: {
                                    // fontFamily: 'inherit',
                                    // fontSize: '16px',
                                    // borderRadius: '10px',
                                // },
                                // icons: {
                                    // search: ''
                                // }
                            // }}
                        // /> */}
                        // <AddressAutocomplete
                            // value={addressInput}
                            // onChange={handleAddressChange}
                            // onSelect={handleAddressSelect}
                            // placeholder="Search for an address"
                        // />
                    
                    // <button type="submit">See my street</button>
                // </form>
                // {error && <p className={styles["error"]}>{error}</p>}
                // <div className={styles["info-container"]}>
                    // <div className={styles["info-step"]}>
                        // <span className={styles["step-number"]}>01</span>
                        // <span className={styles["step-label"]}>Find your street</span>
                    // </div>
                    // <span className={styles["step-arrow"]}>&gt;</span>
                    // <div className={styles["info-step"]}>
                        // <span className={styles["step-number"]}>02</span>
                        // <span className={styles["step-label"]}>Try planting a tree</span>
                    // </div>
                    // <span className={styles["step-arrow"]}>&gt;</span>
                    // <div className={styles["info-step"]}>
                        // <span className={styles["step-number"]}>03</span>
                        // <span className={styles["step-label"]}>See the difference</span>
                    // </div>
                // </div>
            // </div>
            
            // <div className={styles["landing-page-legend-container"]}>
                // <p>TREE CANOPY · ILLUSTRATIVE</p>
                // <div className={styles["legend-color-container"]}>
                    // {colors.map((color) => (
                        // <div key={color.id} className={styles["legend-color-box"]} style={{ backgroundColor: color.color }}></div>
                    // ))}
                // </div>
                // <div className={styles["legend-labels"]}>
                    // <span>Bare</span>
                    // <span>Leafy</span>
                // </div>
            // </div>
        // </div>
    // );

    // Landing v2 (2026-09-03) — Figma "0 · Landing v2".
    // Illustrated map background, hero card top-left, decorative preview card bottom-right.
    // Address logic (handleSubmit / handleAddressSelect / handleAddressChange) is unchanged.
    return (
        <div className={styles["landing-container"]}>
            {/* Brand is a plain wordmark in v2, no square mark */}
            <p className={styles["landing-page-brand"]}>Greenchanger</p>

            <div className={styles["hero-card"]}>
                <h1 className={styles["landing-title"]}>See what one more tree could change.</h1>
                <p className={styles["landing-description"]}>
                    Search a Melbourne address to explore its current tree canopy and preview the shade a new tree could create.
                </p>

                {/* Same AddressAutocomplete + submit as before, only the copy changed */}
                <form className={styles["address-search-container"]} onSubmit={handleSubmit}>
                    <AddressAutocomplete
                        value={addressInput}
                        onChange={handleAddressChange}
                        onSelect={handleAddressSelect}
                        placeholder="Enter a Melbourne address"
                    />
                    {/* aria-label because the text span is hidden on phones (see CSS) */}
                    <button type="submit" aria-label="Explore address">
                        <span className={styles["cta-text"]}>Explore address</span>
                        {/* Arrow as SVG: the U+2192 glyph is not in the Instrument Sans web subset */}
                        <svg className={styles["cta-arrow"]} viewBox="0 0 14 14" fill="none" aria-hidden="true">
                            <path d="M2 7h10M7.5 2.5 12 7l-4.5 4.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                    </button>
                </form>
                {/* role="alert" so screen readers announce the message when it appears */}
                {error && <p role="alert" className={styles["error"]}>{error}</p>}

                <div className={styles["info-container"]}>
                    <div className={styles["info-step"]}>
                        <span className={styles["step-number"]}>01</span>
                        <span className={styles["step-label"]}>Find your street</span>
                    </div>
                    {stepArrow}
                    <div className={styles["info-step"]}>
                        <span className={styles["step-number"]}>02</span>
                        <span className={styles["step-label"]}>Try planting a tree</span>
                    </div>
                    {stepArrow}
                    <div className={styles["info-step"]}>
                        <span className={styles["step-number"]}>03</span>
                        <span className={styles["step-label"]}>See the difference</span>
                    </div>
                </div>
            </div>

            {/* Decorative preview card from the design. The numbers are illustrative only,
                so it is hidden from screen readers and dropped on narrow screens (see CSS). */}
            <div className={styles["sample-result"]} aria-hidden="true">
                <p className={styles["sample-address"]}>15 SEASCAPE STREET, CLAYTON</p>
                <p className={styles["sample-headline"]}>5 trees on this lot</p>
                <p className={styles["sample-delta"]}>+6.6–43.7 m² if you plant one more</p>
                <p className={styles["sample-note"]}>canopy at 10 years · Vicmap + Cybula et al.</p>
            </div>
        </div>
    );
}
