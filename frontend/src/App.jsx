import { useState } from 'react'
import Layout from './components/Layout'
import DashboardPage from './pages/DashboardPage'
import WatchlistPage from './pages/WatchlistPage'
import AgentPage from './pages/AgentPage'
import RiskPage from './pages/RiskPage'
import TradingPage from './pages/TradingPage'
import SettingsPage from './pages/SettingsPage'

function App() {
  const [currentPage, setCurrentPage] = useState('agent')

  const renderPage = () => {
    switch (currentPage) {
      case 'dashboard':
        return <DashboardPage />
      case 'watchlist':
        return <WatchlistPage />
      case 'agent':
        return <AgentPage />
      case 'risk':
        return <RiskPage />
      case 'trading':
        return <TradingPage />
      case 'settings':
        return <SettingsPage />
      default:
        return <AgentPage />
    }
  }

  return (
    <Layout currentPage={currentPage} onNavigate={setCurrentPage}>
      {renderPage()}
    </Layout>
  )
}

export default App
