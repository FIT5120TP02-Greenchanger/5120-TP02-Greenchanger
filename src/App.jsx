import { useState } from 'react'
import LandingPage from './pages/LandingPage.jsx'
import MapView from './pages/MapView.jsx'
import PlantTreePage from './pages/PlantTreePage.jsx';


function App() {
  const [activePage, setActivePage] = useState('landing');
  const [selectedLocation, setSelectedLocation] = useState('');
  const [planTarget, setplanTarget] = useState(null)
  const [simulatedTree, setSimulatedTree] = useState(null);

  const goToPlant = (target) => {
    setplanTarget(target);
    setActivePage('plant')
  }

  const finishPlanting = (tree) => {
    if(tree) setSimulatedTree(tree);
    setActivePage('map')
  }

  return (
    <div style={{ width: '100vw', height: '100vh' }}>

      {activePage === 'landing' && 
      <LandingPage 
      onNavigate={setActivePage}
      selectedLocation={selectedLocation} 
      setSelectedLocation={setSelectedLocation} />}

      {activePage === 'map' && 
      <MapView 
        selectedLocation={selectedLocation} 
        setSelectedLocation={setSelectedLocation}
        simulatedTree={simulatedTree}
        onPlantTree={goToPlant}/>}

      {activePage === 'plant' && 
      <PlantTreePage
      planTarget={planTarget}
      onDone={finishPlanting} />}

    </div>
  )
}

export default App
