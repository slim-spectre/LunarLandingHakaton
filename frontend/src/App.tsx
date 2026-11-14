import { ObservationWorkspace } from './features/observation/ObservationWorkspace'
import { isDemoModeEnabled } from './api/mocks'
import './App.css'

export function App() {
  return (
    <div className="app-container">
      <header className="app-header">
        <div className="header-left">
          <h1 className="app-title" data-testid="app-title">
            Lunar Landing Site Navigator
          </h1>
          <span className="stage-badge">Stage 1</span>
        </div>
        {isDemoModeEnabled() && (
          <span className="demo-badge" data-testid="header-demo-badge">
            DEMO HEALTH FIXTURE · Observations use the API
          </span>
        )}
      </header>
      <ObservationWorkspace />
      <footer className="app-footer">
        <span>Lunar Landing Site Navigator · Geometric observations</span>
        <span>API v1 · All observation times in UTC</span>
      </footer>
    </div>
  )
}

export default App
