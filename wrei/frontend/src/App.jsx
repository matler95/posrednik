import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Hunt from './pages/Hunt';
import ListingDetail from './pages/ListingDetail';
import Stats from './pages/Stats';
import { Layout } from './components/Layout';

function App() {
  return (
    <Router>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Navigate to="/hunt" replace />} />
          <Route path="/hunt" element={<Hunt />} />
          <Route path="/listings/:id" element={<ListingDetail />} />
          <Route path="/stats" element={<Stats />} />
        </Route>
      </Routes>
    </Router>
  );
}

export default App;
