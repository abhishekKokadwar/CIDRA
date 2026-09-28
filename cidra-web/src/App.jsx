import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import RunList from './components/RunList';
import RunDetails from './components/RunDetails';
import { Activity } from 'lucide-react';

function App() {
  return (
    <Router>
      <div className="dashboard-layout">
        <header className="header">
          <Link to="/" style={{ textDecoration: 'none' }}>
            <h1 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Activity size={32} color="#3b82f6" />
              CIDRA Dashboard
            </h1>
          </Link>
          <div className="text-secondary" style={{ fontSize: '0.875rem' }}>
            Phase 13 • Human-in-the-Loop Gate
          </div>
        </header>

        <main>
          <Routes>
            <Route path="/" element={<RunList />} />
            <Route path="/run/:runId" element={<RunDetails />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
