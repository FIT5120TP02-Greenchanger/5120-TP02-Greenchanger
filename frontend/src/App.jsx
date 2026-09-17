import { useState } from 'react'
import LandingPage from './pages/LandingPage.jsx'
import MapView from './pages/MapView.jsx'
// import PlantTreePage from './pages/PlantTreePage.jsx'; // planting now happens inside MapView (2026-09-03)


function App() {
  const [page, setPage] = useState('landing');
  const [selectedLocation, setSelectedLocation] = useState('');
  // In-map planting (2026-09-03): the separate PlantTreePage is no longer used, so there is no
  // planTarget / 'plant' page. simulatedTrees stays here so the scenario survives page changes.
  // const [planTarget, setplanTarget] = useState(null)
  const [simulatedTrees, setSimulatedTrees] = useState(null);

  // const goToPlant = (target) => {
  //   setplanTarget(target);
  //   setPage('plant')
  // }

  // const finishPlanting = (trees) => {
  //   setSimulatedTrees(trees || []);
  //   setPage('map');
  // }

  if (page === 'landing') {
      return <LandingPage onNavigate={setPage} selectedLocation={selectedLocation} setSelectedLocation={setSelectedLocation} />;
    }
    // if (page === 'plant') {
      // return <PlantTreePage planTarget={planTarget} onDone={finishPlanting} />;
    // }
    return (
      <MapView
        selectedLocation={selectedLocation}
        setSelectedLocation={setSelectedLocation}
        simulatedTrees={simulatedTrees}
        // onPlantTree={goToPlant}
        setSimulatedTrees={setSimulatedTrees} // in-map planting writes the scenario here (2026-09-03)
        // Home button on the map page needs a way back to the landing page
        onNavigate={setPage}
      />
    );
}

export default App
