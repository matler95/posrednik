import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { huntApi, createHuntStream, statsApi } from '../api/client';
import { ListingCard } from '../components/ListingCard';
import {
  Target, Play, RefreshCw, Settings, Filter, ChevronDown,
  TrendingUp, BarChart2, Clock, Zap, AlertCircle,
} from 'lucide-react';

const SORT_OPTIONS = [
  { value: 'score', label: 'Score ↓' },
  { value: 'price', label: 'Cena ↑' },
  { value: 'price_per_m2', label: 'Cena/m² ↑' },
  { value: 'date', label: 'Najnowsze' },
];

function StatCard({ label, value, sub, color }) {
  return (
    <div className="card" style={{ padding: '16px 20px' }}>
      <div style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 700, color: color || 'var(--text)', fontFamily: 'JetBrains Mono, monospace', lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: 'var(--text2)', marginTop: 6 }}>{sub}</div>}
    </div>
  );
}

function PortalProgress({ portals_counts, running }) {
  const portals = Object.entries(portals_counts || {});
  if (portals.length === 0 && !running) return null;

  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
      {portals.map(([portal, count]) => (
        <div key={portal} style={{
          background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.2)',
          borderRadius: 6, padding: '3px 10px', fontSize: 11, display: 'flex', gap: 6, alignItems: 'center',
        }}>
          <span style={{ color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{portal}</span>
          <span style={{ color: '#10b981', fontFamily: 'JetBrains Mono, monospace', fontWeight: 600 }}>{count}</span>
        </div>
      ))}
      {running && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--accent)', fontSize: 12 }}>
          <div className="pulse-dot" style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)' }} />
          Skanowanie...
        </div>
      )}
    </div>
  );
}

export default function Hunt() {
  const [status, setStatus] = useState(null);
  const [listings, setListings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [hunting, setHunting] = useState(false);
  const [jobStatus, setJobStatus] = useState(null);
  const [jobProgress, setJobProgress] = useState({ portals_counts: {} });
  const [sortBy, setSortBy] = useState('score');
  const [filterDirect, setFilterDirect] = useState(false);
  const [minScore, setMinScore] = useState(null);
  const [message, setMessage] = useState(null);
  const closeStreamRef = useRef(null);

  useEffect(() => {
    fetchData();
    return () => closeStreamRef.current?.();
  }, []);

  const fetchData = async () => {
    try {
      const [statusRes, listingsRes] = await Promise.all([
        huntApi.status(),
        huntApi.results({ limit: 100, sort_by: sortBy }),
      ]);
      setStatus(statusRes.data);
      setListings(listingsRes.data.listings || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const fetchListings = async () => {
    try {
      const res = await huntApi.results({
        limit: 100,
        sort_by: sortBy,
        direct_only: filterDirect || undefined,
        min_score: minScore || undefined,
      });
      setListings(res.data.listings || []);
    } catch (e) { console.error(e); }
  };

  useEffect(() => { fetchListings(); }, [sortBy, filterDirect, minScore]);

  const handleStartHunt = async () => {
    if (hunting) return;
    setHunting(true);
    setJobProgress({ portals_counts: {} });
    setJobStatus('running');
    setMessage(null);

    try {
      const res = await huntApi.start();
      const { job_id } = res.data;

      closeStreamRef.current?.();
      const close = createHuntStream(
        job_id,
        (event) => {
          if (event.type === 'portal_done') {
            setJobProgress(prev => ({
              ...prev,
              portals_counts: { ...prev.portals_counts, [event.portal]: event.count },
            }));
          }
          if (event.type === 'enriched') {
            fetchListings();
          }
          if (event.type === 'ai_done') {
            // Refresh listing that got AI analysis
            fetchListings();
          }
          if (event.status) setJobStatus(event.status);
        },
        (doneEvent) => {
          setHunting(false);
          setJobStatus('done');
          setMessage({ type: 'success', text: doneEvent.message || 'Polowanie zakończone.' });
          fetchData();
          setTimeout(() => setMessage(null), 5000);
        },
        () => {
          setHunting(false);
          setJobStatus('error');
        }
      );
      closeStreamRef.current = close;
    } catch (e) {
      setHunting(false);
      setMessage({ type: 'error', text: 'Błąd uruchomienia polowania.' });
    }
  };

  const opportunities = listings.filter(l => (l.score || 0) >= 0.25);
  const cfg = status?.config || {};

  const huntSummary = [
    cfg.max_price ? `do ${(cfg.max_price / 1000).toFixed(0)}k PLN` : null,
    cfg.max_area ? `do ${cfg.max_area} m²` : null,
    cfg.districts?.length ? cfg.districts.slice(0, 2).join(', ') : 'Warszawa',
  ].filter(Boolean).join(' · ');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 10 }}>
            <Target size={22} color="var(--accent)" />
            Centrum Polowania
          </h1>
          <p style={{ margin: '6px 0 0', color: 'var(--text2)', fontSize: 14 }}>
            {huntSummary || 'Skonfiguruj profil polowania'}
          </p>
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <Link to="/hunt/settings" style={{ textDecoration: 'none' }}>
            <button className="btn btn-ghost">
              <Settings size={15} />
              Profil
            </button>
          </Link>
          <button
            className="btn btn-primary"
            onClick={handleStartHunt}
            disabled={hunting}
            style={{ minWidth: 140 }}
          >
            {hunting ? (
              <><RefreshCw size={15} style={{ animation: 'spin 1s linear infinite' }} /> Polowanie...</>
            ) : (
              <><Play size={15} /> Zacznij polowanie</>
            )}
          </button>
        </div>
      </div>

      {/* Message */}
      {message && (
        <div style={{
          background: message.type === 'success' ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
          border: `1px solid ${message.type === 'success' ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'}`,
          borderRadius: 8, padding: '10px 16px', fontSize: 13,
          color: message.type === 'success' ? '#10b981' : '#ef4444',
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          {message.type === 'success' ? <Zap size={14} /> : <AlertCircle size={14} />}
          {message.text}
        </div>
      )}

      {/* Progress */}
      {hunting && (
        <div className="card" style={{ padding: '14px 20px' }}>
          <div style={{ marginBottom: 10 }}>
            <div style={{
              height: 3, background: 'rgba(255,255,255,0.06)', borderRadius: 2, overflow: 'hidden',
            }}>
              <div className="progress-animated" style={{ height: '100%', width: '100%', borderRadius: 2 }} />
            </div>
          </div>
          <PortalProgress portals_counts={jobProgress.portals_counts} running={hunting} />
        </div>
      )}

      {/* Stats row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        <StatCard
          label="W bazie"
          value={status?.total_listings ?? '—'}
          sub="łącznie ofert"
        />
        <StatCard
          label="Okazje"
          value={status?.opportunities ?? opportunities.length}
          sub="score ≥ 25%"
          color="#10b981"
        />
        <StatCard
          label="Analiza AI"
          value={status?.pending_ai ?? '—'}
          sub="oczekuje"
          color="#f59e0b"
        />
        <StatCard
          label="Portale"
          value={(cfg.portals || ['otodom', 'olx']).length}
          sub={(cfg.portals || ['otodom', 'olx']).join(' · ')}
        />
      </div>

      {/* Filters bar */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--text2)' }}>
          <Filter size={14} />
          Sortuj:
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {SORT_OPTIONS.map(opt => (
            <button
              key={opt.value}
              onClick={() => setSortBy(opt.value)}
              style={{
                padding: '5px 12px', borderRadius: 6, fontSize: 12, cursor: 'pointer', border: 'none',
                background: sortBy === opt.value ? 'var(--accent)' : 'var(--bg3)',
                color: sortBy === opt.value ? 'white' : 'var(--text2)',
                fontFamily: 'inherit', fontWeight: 500,
                transition: 'all 0.15s',
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', gap: 8, marginLeft: 'auto', alignItems: 'center' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer', color: 'var(--text2)' }}>
            <input
              type="checkbox"
              checked={filterDirect}
              onChange={e => setFilterDirect(e.target.checked)}
              style={{ accentColor: 'var(--accent)' }}
            />
            Tylko bezpośrednie
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer', color: 'var(--text2)' }}>
            <input
              type="checkbox"
              checked={minScore === 0.25}
              onChange={e => setMinScore(e.target.checked ? 0.25 : null)}
              style={{ accentColor: 'var(--accent)' }}
            />
            Tylko okazje
          </label>
        </div>
      </div>

      {/* Listings */}
      {loading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {[1, 2, 3].map(i => (
            <div key={i} className="card" style={{ height: 140, background: 'var(--bg2)' }} />
          ))}
        </div>
      ) : listings.length === 0 ? (
        <div className="card" style={{ padding: 60, textAlign: 'center' }}>
          <Target size={40} color="var(--muted)" style={{ opacity: 0.3, marginBottom: 16 }} />
          <div style={{ color: 'var(--text2)', marginBottom: 8 }}>Brak ofert w bazie</div>
          <div style={{ fontSize: 13, color: 'var(--muted)' }}>
            Uruchom polowanie lub dostosuj parametry w konfiguracji.
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ fontSize: 13, color: 'var(--muted)' }}>
            {listings.length} ofert · {opportunities.length} okazji
          </div>
          {listings.map(l => <ListingCard key={l.id} listing={l} />)}
        </div>
      )}

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}