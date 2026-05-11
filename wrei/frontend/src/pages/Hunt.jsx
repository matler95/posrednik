import { useState, useEffect } from 'react';
import { huntApi } from '../api/client';
import { ListingCard } from '../components/ListingCard';
import { Target, TrendingUp, AlertCircle, Search, RefreshCw, SlidersHorizontal } from 'lucide-react';

export default function Hunt() {
  const [status, setStatus] = useState(null);
  const [listings, setListings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('opportunities');

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [statusRes, listingsRes] = await Promise.all([
        huntApi.getStatus(),
        huntApi.getListings()
      ]);
      setStatus(statusRes.data);
      setListings(listingsRes.data.listings);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const opportunities = listings.filter(l => l.score >= 0.25);

  return (
    <div className="space-y-8 animate-in fade-in duration-700">
      {/* Header & Status */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
           <h1 className="text-3xl font-black text-white flex items-center gap-3">
             <Target className="text-premium-accent w-8 h-8" />
             Centrum Dowodzenia
           </h1>
           <p className="text-premium-muted mt-1">
             Aktywne polowanie: <span className="text-white font-semibold">{status?.config?.city_slug || 'Warszawa'}</span> • 
             Budżet: <span className="text-white font-semibold">&lt; {status?.config?.max_price?.toLocaleString()} PLN</span>
           </p>
        </div>
        <div className="flex gap-3">
          <button 
            onClick={fetchData} 
            disabled={loading}
            className="p-3 bg-slate-800 hover:bg-slate-700 rounded-xl border border-slate-700 transition-all active:scale-95 disabled:opacity-50"
          >
            <RefreshCw className={loading ? "animate-spin w-5 h-5" : "w-5 h-5"} />
          </button>
          <button className="btn-primary flex items-center gap-2">
            <SlidersHorizontal className="w-4 h-4" />
            Konfiguracja
          </button>
        </div>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <StatsCard 
          label="W bazie" 
          value={status?.total_listings || 0} 
          sub="Łącznie ofert" 
          icon={Search} 
        />
        <StatsCard 
          label="Okazje" 
          value={opportunities.length} 
          sub="Score > 25%" 
          icon={TrendingUp} 
          color="text-emerald-400"
        />
        <StatsCard 
          label="Ostatni run" 
          value={status?.last_run ? new Date(status.last_run).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : 'Brak'} 
          sub={status?.last_run ? new Date(status.last_run).toLocaleDateString() : 'Czekam na start'} 
          icon={RefreshCw} 
        />
        <StatsCard 
          label="Alerty" 
          value={0} 
          sub="Dzisiaj wysłano" 
          icon={AlertCircle} 
        />
      </div>

      {/* Tabs & Content */}
      <div className="space-y-6">
        <div className="flex border-b border-slate-700/50 gap-8 overflow-x-auto no-scrollbar">
          <TabButton active={tab === 'opportunities'} onClick={() => setTab('opportunities')}>Okazje ({opportunities.length})</TabButton>
          <TabButton active={tab === 'all'} onClick={() => setTab('all')}>Wszystkie ({listings.length})</TabButton>
          <TabButton active={tab === 'map'} onClick={() => setTab('map')}>Mapa</TabButton>
        </div>

        <div className="grid grid-cols-1 gap-6">
          {loading ? (
             Array.from({ length: 3 }).map((_, i) => (
               <div key={i} className="card-premium h-48 animate-pulse bg-slate-800/50" />
             ))
          ) : (
            <>
              {tab === 'opportunities' && (
                opportunities.length > 0 ? (
                  opportunities.map(l => <ListingCard key={l.id} listing={l} />)
                ) : (
                  <EmptyState message="Brak okazji spełniających kryteria. Spróbuj poluzować filtry." />
                )
              )}
              {tab === 'all' && (
                listings.length > 0 ? (
                  listings.map(l => <ListingCard key={l.id} listing={l} />)
                ) : (
                  <EmptyState message="Brak ofert w bazie. Uruchom skanowanie." />
                )
              )}
              {tab === 'map' && (
                <div className="card-premium h-[500px] flex items-center justify-center bg-slate-800/30 border-dashed">
                   <p className="text-premium-muted">Moduł mapy w trakcie integracji...</p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function StatsCard({ label, value, sub, icon: Icon, color = "text-white" }) {
  return (
    <div className="card-premium">
      <div className="flex justify-between items-start mb-4">
        <span className="text-xs font-bold text-premium-muted uppercase tracking-wider">{label}</span>
        <div className="p-2 bg-slate-800 rounded-lg">
          <Icon className="w-4 h-4 text-premium-accent" />
        </div>
      </div>
      <div className={`text-3xl font-black tracking-tight ${color}`}>{value}</div>
      <div className="text-xs text-premium-muted mt-1 font-medium">{sub}</div>
    </div>
  );
}

function TabButton({ children, active, onClick }) {
  return (
    <button 
      onClick={onClick}
      className={`pb-4 text-sm font-bold transition-all relative whitespace-nowrap ${active ? 'text-premium-accent' : 'text-premium-muted hover:text-white'}`}
    >
      {children}
      {active && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-premium-accent rounded-full shadow-[0_0_8px_rgba(59,130,246,0.5)]" />}
    </button>
  );
}

function EmptyState({ message }) {
  return (
    <div className="text-center py-20 card-premium bg-slate-800/20 border-dashed">
      <Target className="w-12 h-12 text-slate-700 mx-auto mb-4" />
      <p className="text-premium-muted font-medium">{message}</p>
    </div>
  );
}
