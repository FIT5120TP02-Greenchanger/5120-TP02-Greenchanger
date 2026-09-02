import styles from './LandingPage.module.css';
// import { SearchBox } from '@mapbox/search-js-react';
import AddressAutocomplete from '../components/AddressAutocomplete';
import { useState } from 'react';

const colors = [
    {id: 1, color: "#E9E2D0"},
    {id: 2, color: "#DFDCC4"},
    {id: 3, color: "#CFD6B4"},
    {id: 4, color: "#B7CB9E"},
    {id: 5, color: "#95B884"},
    {id: 6, color: "#6DA269"},
    {id: 7, color: "#3F7A52"}
];

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

    return (
        <div className={styles["landing-container"]}>
            <div className={styles["landing-page-brand"]}>
                <div className={styles["landing-page-mark"]}></div>
                <p>Green Changer</p>
            </div>

            <div className={styles["hero-card"]}>
                <h1 className={styles["landing-title"]}>Some Melbourne streets have four times the tree canopy of others</h1>
                <p className={styles["landing-description"]}>
                    Find out where you sits - and see what one more tree would actually change.
                </p>
                <form className={styles["address-search-container"]} onSubmit={handleSubmit}>
                        {/* <SearchBox
                            accessToken={import.meta.env.VITE_MAPBOX_ACCESS_TOKEN}
                            onRetrieve={handleAddressSelect}
                            onChange={handleAddressChange}
                            value={addressInput}
                            placeholder="Search for an address"
                            options={{
                                country: 'AU',
                                language: 'en',
                                types: 'address',
                                bbox: [
                                    144.4,
                                    -38.3,
                                    145.5,
                                    -37.4
                                ]
                            }}
                            theme={{
                                variables: {
                                    fontFamily: 'inherit',
                                    fontSize: '16px',
                                    borderRadius: '10px',
                                },
                                icons: {
                                    search: ''
                                }
                            }}
                        /> */}
                        <AddressAutocomplete
                            value={addressInput}
                            onChange={handleAddressChange}
                            onSelect={handleAddressSelect}
                            placeholder="Search for an address"
                        />
                    
                    <button type="submit">See my street</button>
                </form>
                {error && <p className={styles["error"]}>{error}</p>}
                <div className={styles["info-container"]}>
                    <div className={styles["info-step"]}>
                        <span className={styles["step-number"]}>01</span>
                        <span className={styles["step-label"]}>Find your street</span>
                    </div>
                    <span className={styles["step-arrow"]}>&gt;</span>
                    <div className={styles["info-step"]}>
                        <span className={styles["step-number"]}>02</span>
                        <span className={styles["step-label"]}>Try planting a tree</span>
                    </div>
                    <span className={styles["step-arrow"]}>&gt;</span>
                    <div className={styles["info-step"]}>
                        <span className={styles["step-number"]}>03</span>
                        <span className={styles["step-label"]}>See the difference</span>
                    </div>
                </div>
            </div>
            
            <div className={styles["landing-page-legend-container"]}>
                <p>TREE CANOPY · ILLUSTRATIVE</p>
                <div className={styles["legend-color-container"]}>
                    {colors.map((color) => (
                        <div key={color.id} className={styles["legend-color-box"]} style={{ backgroundColor: color.color }}></div>
                    ))}
                </div>
                <div className={styles["legend-labels"]}>
                    <span>Bare</span>
                    <span>Leafy</span>
                </div>
            </div>
        </div>
    );
}
