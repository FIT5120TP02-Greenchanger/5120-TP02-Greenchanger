import { useState } from 'react'
import LandingPage from './pages/LandingPage.jsx'
import MapView from './pages/MapView.jsx'
import PlantTreePage from './pages/PlantTreePage.jsx';


function App() {
  const [page, setPage] = useState('landing');
  const [selectedLocation, setSelectedLocation] = useState('');
  const [planTarget, setplanTarget] = useState(null)
  const [simulatedTree, setSimulatedTree] = useState(null);

  const goToPlant = (target) => {
    setplanTarget(target);
    setPage('plant')
  }

  const finishPlanting = (tree) => {
    setSimulatedTree(tree);
    setPage('map')
  }

  if (page === 'landing') {
      return <LandingPage onNavigate={setPage} selectedLocation={selectedLocation} setSelectedLocation={setSelectedLocation} />;
    }
    if (page === 'plant') {
      return <PlantTreePage planTarget={planTarget} onDone={finishPlanting} />;
    }
    return (
      <MapView
        selectedLocation={selectedLocation}
        setSelectedLocation={setSelectedLocation}
        simulatedTree={simulatedTree}
        onPlantTree={goToPlant}
      />
    );
}

export default App
