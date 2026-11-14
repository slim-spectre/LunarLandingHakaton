import React from 'react'
import { HealthCard } from './features/health/HealthCard'
import { MapSlot } from './components/MapSlot'
import { SceneSlot } from './components/SceneSlot'
import { AnalyticsSlot } from './components/AnalyticsSlot'
import { isDemoModeEnabled } from './api/mocks'
import './App.css'

export const App: React.FC = () => {
  const isDemo = isDemoModeEnabled()

  return (
    <div className="app-container">
      <header className="app-header">
        <div className="header-left">
          <h1 className="app-title" data-testid="app-title">
            Lunar Landing Site Navigator
          </h1>
          <span className="stage-badge">Stage 0 Baseline</span>
        </div>

        <div className="header-right">
          {isDemo && (
            <div className="header-demo-indicator" data-testid="header-demo-badge">
              <span className="demo-badge">DEMO / TEST DATA ACTIVE</span>
            </div>
          )}
        </div>
      </header>

      <main className="app-main">
        <div className="main-grid">
          <aside className="grid-sidebar">
            <HealthCard />
            <AnalyticsSlot />
          </aside>

          <section className="grid-content">
            <MapSlot />
            <SceneSlot />
          </section>
        </div>
      </main>

      <footer className="app-footer">
        <span>Lunar Landing Site Navigator &bull; Stage 0 Foundations</span>
        <span>Agreed API Contract v1 &bull; NASA Artemis & CLPS Target Support</span>
      </footer>
    </div>
  )
}

export default App
