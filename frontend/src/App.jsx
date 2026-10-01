import { useState } from 'react'
import LandingPage from './pages/LandingPage.jsx'
import MapView from './pages/MapView.jsx'
import ChatbotWidget from './components/ChatbotWidget.jsx'
import { buildChatbotTrees, buildChatbotSpeciesCatalogue } from './utils/chatbotContext'

function App() {
  const [page, setPage] = useState('landing');
  const [selectedLocation, setSelectedLocation] = useState('');
  // In-map planting (2026-09-03): the separate PlantTreePage is no longer used, so there is no
  // planTarget / 'plant' page. simulatedTrees stays here so the scenario survives page changes.
  // const [planTarget, setplanTarget] = useState(null)
  const [simulatedTrees, setSimulatedTrees] = useState(null);

  const [propertyStats, setPropertyStats] = useState(null);
  const [speciesCatalogue, setSpeciesCatalogue] = useState([])

  const chatbotSpeciesCatalogue = buildChatbotSpeciesCatalogue(speciesCatalogue)
  const chatbotTrees = buildChatbotTrees(simulatedTrees)
  return (
    <>
      {page === 'landing' && <LandingPage onNavigate={setPage} selectedLocation={selectedLocation} setSelectedLocation={setSelectedLocation} />}
      {page !== 'landing' && 
        <>
          <ChatbotWidget
              context={
                  page === 'map'
                      ? {
                          property: {
                            address: propertyStats?.address,
                            canopy_pct: propertyStats?.canopyPct,
                            tree_count: propertyStats?.treeCount,
                            land_surface_temp_c: propertyStats?.landSurfaceTempC,
                            neighbourhood_canopy_pct:
                              propertyStats?.neighbourhoodCanopyPct,
                          },

                          simulation: {
                            tree_count: chatbotTrees.length,
                            trees: chatbotTrees,
                          },
                          speciesCatalogue: chatbotSpeciesCatalogue,
                        }
                      : null
              }
          />
          <MapView
            selectedLocation={selectedLocation}
            setSelectedLocation={setSelectedLocation}
            simulatedTrees={simulatedTrees}
            // onPlantTree={goToPlant}
            setSimulatedTrees={setSimulatedTrees} // in-map planting writes the scenario here (2026-09-03)
            // Home button on the map page needs a way back to the landing page
            onNavigate={setPage}
            onPropertyStatsChange={setPropertyStats}

            speciesCatalogue={speciesCatalogue}
            setSpeciesCatalogue={setSpeciesCatalogue}
          />
        </>
      }
    </>
  );
}

export default App
