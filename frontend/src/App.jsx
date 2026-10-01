import { useState } from 'react'
import LandingPage from './pages/LandingPage.jsx'
import MapView from './pages/MapView.jsx'
import ChatbotWidget from './components/ChatbotWidget.jsx'

function App() {
  const [page, setPage] = useState('landing');
  const [selectedLocation, setSelectedLocation] = useState('');
  // In-map planting (2026-09-03): the separate PlantTreePage is no longer used, so there is no
  // planTarget / 'plant' page. simulatedTrees stays here so the scenario survives page changes.
  // const [planTarget, setplanTarget] = useState(null)
  const [simulatedTrees, setSimulatedTrees] = useState(null);

  const [propertyStats, setPropertyStats] = useState(null);
  const [speciesCatalogue, setSpeciesCatalogue] = useState([])

  const chatbotSpeciesCatalogue = speciesCatalogue.map(species => ({
      scientific_name: species.scientific_name,
      common_name: species.common_name,
      has_growth_model: species.has_growth_model,
  }));
  
  const chatbotTrees = (simulatedTrees || []).map((tree, index) => ({
    tree_number: index + 1,
    species: tree.scenario.species?.common_name,
    scientific_name: tree.scenario.species?.scientific_name,
    size: tree.scenario.size,

    growth: tree.scenario?.growth
      ? {
          canopy_m2_min: tree.scenario.growth.canopy_m2_min,
          canopy_m2_median: tree.scenario.growth.canopy_m2_median,
          canopy_m2_max: tree.scenario.growth.canopy_m2_max,
          height_m_min: tree.scenario.growth.height_m_min,
          height_m_median: tree.scenario.growth.height_m_median,
          height_m_max: tree.scenario.growth.height_m_max,
          crown_width_m_min: tree.scenario.growth.crown_width_m_min,
          crown_width_m_median: tree.scenario.growth.crown_width_m_median,
          crown_width_m_max: tree.scenario.growth.crown_width_m_max,
          timeframe_years: tree.scenario.growth.equivalent_age_years,
        }
      : null,

    impact: tree.scenario?.impact
      ? {
          impact_area_m2_min: tree.scenario.impact.impact_area_range_m2.minimum,
          impact_area_m2_max: tree.scenario.impact.impact_area_range_m2.maximum,
          temperature_change_c_min:
            tree.scenario.impact.temperature_change_range_c.minimum,
          temperature_change_c_max:
            tree.scenario.impact.temperature_change_range_c.maximum,
          projected_canopy_m2_min:
            tree.scenario.impact.projected_canopy_range_m2.minimum,
          projected_canopy_m2_max:
            tree.scenario.impact.projected_canopy_range_m2.maximum,
        }
      : null,

    cost: tree.scenario?.costs
      ? {
          min_aud: tree.scenario.costs?.minimum_cost,
          max_aud: tree.scenario.costs?.maximum_cost,
          currency: tree.scenario.costs?.currency
        }
      : null,
    position: tree.scenario?.position
  }));
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
