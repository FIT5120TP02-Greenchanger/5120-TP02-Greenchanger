import { useState } from 'react'
import LandingPage from './pages/LandingPage.jsx'
import MapView from './pages/MapView.jsx'
import ChatbotWidget from './components/ChatbotWidget.jsx'
// import PlantTreePage from './pages/PlantTreePage.jsx'; // planting now happens inside MapView (2026-09-03)


function App() {
  const [page, setPage] = useState('landing');
  const [selectedLocation, setSelectedLocation] = useState('');
  // In-map planting (2026-09-03): the separate PlantTreePage is no longer used, so there is no
  // planTarget / 'plant' page. simulatedTrees stays here so the scenario survives page changes.
  // const [planTarget, setplanTarget] = useState(null)
  const [simulatedTrees, setSimulatedTrees] = useState(null);

  const [propertyStats, setPropertyStats] = useState(null);
  const [canopyStats, setCanopyStats] = useState(null);
  const [currentScenario, setCurrentScenario] = useState(null);

  return (
    <>
      {page === 'landing' && <LandingPage onNavigate={setPage} selectedLocation={selectedLocation} setSelectedLocation={setSelectedLocation} />}
      {page !== 'landing' && 
      <MapView
        selectedLocation={selectedLocation}
        setSelectedLocation={setSelectedLocation}
        simulatedTrees={simulatedTrees}
        // onPlantTree={goToPlant}
        setSimulatedTrees={setSimulatedTrees} // in-map planting writes the scenario here (2026-09-03)
        // Home button on the map page needs a way back to the landing page
        onNavigate={setPage}
        onPropertyStatsChange={setPropertyStats}
        onCanopyStatsChange={setCanopyStats}
        onScenarioChange={setCurrentScenario}
      />}
      <ChatbotWidget
          context={
              page === 'map'
                  ? {
                      propertyStats,
                      canopyStats,
                      simulatedTrees,
                      currentScenario
                  }
                  : null
          }
      />
    </>
  );
}

export default App
