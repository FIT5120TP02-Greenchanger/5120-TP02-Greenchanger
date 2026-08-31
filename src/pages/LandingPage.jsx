import styles from './LandingPage.module.css';
import { SearchBox } from '@mapbox/search-js-react';
import { useState } from 'react';

export default function LandingPage({onNavigate, selectedLocation, setSelectedLocation}) {
    const [addressInput, setAddressInput] = useState(selectedLocation?.address || "");

    const handleSubmit = (e) => {
        e.preventDefault();
        if (!selectedLocation?.address?.trim()) return;
        console.log("Submitted address:", selectedLocation);

        onNavigate('map');
    }

    const handleAddressSelect = (location) => {
        const feature = location.features?.[0];
        if (!feature) return;
        const coordinates = feature.geometry?.coordinates;
        const label = feature.properties?.full_address || feature.properties?.name || addressInput;

        setSelectedLocation(
            {
                address: label,
                coordinates
            }
        );
        setAddressInput(label);
    };
    const handleAddressChange = (location) => {
        setSelectedLocation(null);
        setAddressInput(location);
    };

    return (
        <div className={styles["landing-container"]}>
            <div className={styles["hero-card"]}>
                <h1 className={styles["landing-title"]}>Some Melbourne streets have four times the tree canopy of others</h1>
                <p className={styles["landing-description"]}>
                    Find out where you sits - and see what one more tree would actually change.
                </p>
                <form className={styles["address-search-container"]} onSubmit={handleSubmit}>
                    <div className={styles["search-box-container"]}>
                        <SearchBox
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
                        />
                    </div>
                    
                    <button type="submit">See my street</button>
                </form>
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
        </div>
    );
}