import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Hunt from './pages/Hunt';
import ListingDetail from './pages/ListingDetail';
import Stats from './pages/Stats';
import Settings from './pages/Settings';
import Alerts from './pages/Alerts';
import { Layout } from './components/Layout';

function App() {
  return (
    <Router>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Navigate to="/hunt" replace />} />
          <Route path="/hunt" element={<Hunt />} />
          <Route path="/hunt/settings" element={<Settings />} />
          <Route path="/listings/:id" element={<ListingDetail />} />
          <Route path="/stats" element={<Stats />} />
          <Route path="/alerts" element={<Alerts />} />
        </Route>
      </Routes>
    </Router>
  );
}

export default App;
