import { useState, useEffect, useRef, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { huntApi, createHuntStream } from '../api/client';
import {
  Target, Play, RefreshCw, Settings, Filter, ExternalLink,
  TrendingDown, TrendingUp, Zap, AlertCircle, User, Building,
  ChevronDown, ChevronUp, MapPin, Maximize2, Hash,
} from 'lucide-react';

// ─── helpers ─────────────────────────────────────────────────────────────────

function fmt(n, decimals = 0) {
  if (n == null || isNaN(n)) return '—';
  return Number(n).toLocaleString('pl-PL', { maximumFractionDigits: decimals });
}

function scoreColor(s) {
  if (s >= 0.5) return '#10b981';
  if (s >= 0.3) return '#f59e0b';
  if (s >= 0.15) return '#60a5fa';
  return '#5b6882';
}

// ─── ScorePill ────────────────────────────────────────────────────────────────

function ScorePill({ score }) {
  const pct = Math.round((score || 0) * 100);
  const color = scoreColor(score || 0);
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      background: `${color}18`, border: `1px solid ${color}44`,
      borderRadius: 10, padding: '8px 14px', minWidth: 58, flexShrink: 0,
    }}>
      <span style={{ fontSize: 22, fontWeight: 700, color, fontFamily: 'JetBrains Mono, monospace', lineHeight: 1 }}>
        {pct}
      </span>
      <span style={{ fontSize: 9, color: 'var(--muted)', letterSpacing: '0.1em', textTransform: 'uppercase', marginTop: 2 }}>
        score
      </span>
    </div>
  );
}

// ─── ScoreBreakdown ───────────────────────────────────────────────────────────

function ScoreBreakdown({ components, inputs }) {
  if (!components) return null;
  const bars = [
    { key: 'price_gap', label: 'ML gap', max: 0.35 },
    { key: 'txn_gap', label: 'RCN gap', max: 0.30 },
    { key: 'market_pos', label: 'Rynek', max: 0.15 },
    { key: 'freshness', label: 'Świeżość', max: 0.12 },
    { key: 'direct', label: 'Bezpośr.', max: 0.08 },
    { key: 'text_boost', label: 'AI text', max: 0.08 },
  ];
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 8 }}>
      {bars.map(({ key, label, max }) => {
        const val = components[key] || 0;
        const pct = Math.min(100, Math.round((val / max) * 100));
        const color = pct >= 70 ? '#10b981' : pct >= 35 ? '#f59e0b' : '#5b6882';
        return (
          <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 10, color: 'var(--muted)', minWidth: 62, textAlign: 'right' }}>{label}</span>
            <div style={{ flex: 1, height: 4, background: 'rgba(255,255,255,0.07)', borderRadius: 2, overflow: 'hidden' }}>
              <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 2, transition: 'width 0.5s ease' }} />
            </div>
            <span style={{ fontSize: 10, color, fontFamily: 'JetBrains Mono, monospace', minWidth: 32, textAlign: 'right' }}>
              {(val * 100).toFixed(1)}%
            </span>
          </div>
        );
      })}
      {inputs?.rcn_fallback && (
        <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 2, fontStyle: 'italic' }}>
          ⚠ benchmark z market_stats (brak RCN dla dzielnicy)
        </div>
      )}
    </div>
  );
}

// ─── ListingCard (pełna wersja snajper) ───────────────────────────────────────

function ListingCard({ listing }) {
  const [expanded, setExpanded] = useState(false);
  const {
    id, title, price, area, district, rooms,
    score, score_components, transaction_gap, images, direct_offer,
    rcn_benchmark, price_per_m2, llm_analysis, portal,
    days_on_market, condition, estimated_value, cagr_5y,
  } = listing;

  const img = Array.isArray(images) && images.length > 0
    ? (typeof images[0] === 'string' ? images[0] : images[0]?.url)
    : null;

  const gap = transaction_gap != null ? transaction_gap : null;
  const gapPct = gap != null ? Math.abs(Math.round(gap * 100)) : null;
  const gapPos = gap != null && gap > 0;
  const psm = price_per_m2 || (price && area ? Math.round(price / area) : null);
  const savings = (rcn_benchmark && psm && area)
    ? Math.round((rcn_benchmark - psm) * area)
    : null;

  const aiSummary = llm_analysis?.summary;
  const greenFlags = llm_analysis?.green_flags || [];
  const redFlags = llm_analysis?.red_flags || [];
  const hasAI = !!(aiSummary || greenFlags.length || redFlags.length);

  const sc = score_components?.components;
  const si = score_components?.inputs;

  return (
    <div className="card fade-in" style={{ padding: 0, overflow: 'hidden' }}>
      <div style={{ display: 'flex' }}>
        {/* Thumbnail */}
        <div style={{ width: 180, flexShrink: 0, background: 'var(--bg3)', position: 'relative', minHeight: 140 }}>
          {img ? (
            <img src={img} alt={title} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
          ) : (
            <div style={{ height: 140, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Building size={28} color="var(--muted)" style={{ opacity: 0.3 }} />
            </div>
          )}
          {direct_offer && (
            <div style={{
              position: 'absolute', top: 8, left: 8,
              background: '#10b981', color: '#fff',
              fontSize: 9, fontWeight: 700, padding: '2px 6px', borderRadius: 4,
              letterSpacing: '0.08em', textTransform: 'uppercase',
            }}>
              <User size={9} style={{ display: 'inline', marginRight: 3 }} />
              Bezpośrednia
            </div>
          )}
          {days_on_market === 0 && (
            <div style={{
              position: 'absolute', bottom: 8, left: 8,
              background: 'rgba(59,130,246,0.9)', color: '#fff',
              fontSize: 9, fontWeight: 700, padding: '2px 6px', borderRadius: 4,
            }}>Nowe</div>
          )}
        </div>

        {/* Main content */}
        <div style={{ flex: 1, padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 8, minWidth: 0 }}>
          {/* Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
            <div style={{ minWidth: 0 }}>
              <div style={{
                fontSize: 15, fontWeight: 600, color: 'var(--text)',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {title || 'Bez tytułu'}
              </div>
              <div style={{ display: 'flex', gap: 10, marginTop: 4, flexWrap: 'wrap' }}>
                {district && (
                  <span style={{ fontSize: 12, color: 'var(--text2)', display: 'flex', alignItems: 'center', gap: 3 }}>
                    <MapPin size={11} />{district}
                  </span>
                )}
                {area && (
                  <span style={{ fontSize: 12, color: 'var(--text2)', display: 'flex', alignItems: 'center', gap: 3 }}>
                    <Maximize2 size={11} />{area} m²
                  </span>
                )}
                {rooms && (
                  <span style={{ fontSize: 12, color: 'var(--text2)', display: 'flex', alignItems: 'center', gap: 3 }}>
                    <Hash size={11} />{rooms} pok.
                  </span>
                )}
                {portal && (
                  <span style={{ fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    {portal}
                  </span>
                )}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', flexShrink: 0 }}>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 19, fontWeight: 700, color: 'var(--text)', lineHeight: 1 }}>
                  {fmt(price)} <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--muted)' }}>PLN</span>
                </div>
                {psm && (
                  <div style={{ fontSize: 11, color: 'var(--text2)', marginTop: 3, fontFamily: 'JetBrains Mono, monospace' }}>
                    {fmt(psm)} zł/m²
                  </div>
                )}
              </div>
              <ScorePill score={score} />
            </div>
          </div>

          {/* Metrics row */}
          <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', alignItems: 'center' }}>
            {gap != null && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 5,
                background: gapPos ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)',
                border: `1px solid ${gapPos ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)'}`,
                borderRadius: 6, padding: '4px 9px', fontSize: 12,
              }}>
                {gapPos ? <TrendingDown size={12} color="#10b981" /> : <TrendingUp size={12} color="#ef4444" />}
                <span style={{ color: gapPos ? '#10b981' : '#ef4444', fontWeight: 600 }}>
                  {gapPos ? '-' : '+'}{gapPct}% vs RCN
                </span>
              </div>
            )}
            {savings != null && savings > 0 && (
              <div style={{
                background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.2)',
                borderRadius: 6, padding: '4px 9px', fontSize: 12,
                color: '#10b981', fontWeight: 600,
              }}>
                Oszczędność: {fmt(savings)} PLN
              </div>
            )}
            {rcn_benchmark && (
              <div style={{
                background: 'rgba(255,255,255,0.04)', borderRadius: 6, padding: '4px 9px',
                fontSize: 12, color: 'var(--text2)',
              }}>
                RCN: <span style={{ color: 'var(--text)', fontFamily: 'JetBrains Mono, monospace' }}>
                  {fmt(Math.round(rcn_benchmark))} zł/m²
                </span>
              </div>
            )}
            {condition && (
              <div style={{
                background: 'rgba(255,255,255,0.04)', borderRadius: 6, padding: '4px 9px',
                fontSize: 11, color: 'var(--text2)', textTransform: 'capitalize',
              }}>
                {condition}
              </div>
            )}
            {cagr_5y != null && (
              <div style={{
                background: 'rgba(255,255,255,0.04)', borderRadius: 6, padding: '4px 9px',
                fontSize: 11, color: cagr_5y >= 0 ? '#10b981' : '#ef4444',
              }}>
                CAGR 5Y: {cagr_5y >= 0 ? '+' : ''}{(cagr_5y * 100).toFixed(1)}%
              </div>
            )}
          </div>

          {/* AI summary */}
          {aiSummary && (
            <div style={{
              background: 'rgba(59,130,246,0.05)',
              border: '1px solid rgba(59,130,246,0.12)',
              borderRadius: 7, padding: '8px 12px',
              display: 'flex', gap: 8, alignItems: 'flex-start',
            }}>
              <Zap size={12} color="var(--accent)" style={{ flexShrink: 0, marginTop: 2 }} />
              <p style={{ margin: 0, fontSize: 12, color: 'var(--text2)', lineHeight: 1.6 }}>
                {aiSummary}
              </p>
            </div>
          )}

          {/* Actions row */}
          <div style={{ display: 'flex', gap: 7, alignItems: 'center', marginTop: 2 }}>
            <Link to={`/listings/${id}`} style={{ textDecoration: 'none' }}>
              <button className="btn btn-primary" style={{ padding: '6px 14px', fontSize: 12 }}>
                Szczegóły
              </button>
            </Link>
            {listing.url && (
              <a href={listing.url} target="_blank" rel="noreferrer" style={{ textDecoration: 'none' }}>
                <button className="btn btn-ghost" style={{ padding: '6px 12px', fontSize: 12 }}>
                  <ExternalLink size={12} /> Ogłoszenie
                </button>
              </a>
            )}
            {(sc || greenFlags.length > 0 || redFlags.length > 0) && (
              <button
                className="btn btn-ghost"
                style={{ padding: '6px 12px', fontSize: 12, marginLeft: 'auto' }}
                onClick={() => setExpanded(e => !e)}
              >
                {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                {expanded ? 'Mniej' : 'Score breakdown'}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Expandable: score breakdown + AI flags */}
      {expanded && (
        <div style={{
          borderTop: '1px solid var(--border)',
          padding: '14px 18px',
          display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20,
          background: 'rgba(255,255,255,0.015)',
        }}>
          {sc && (
            <div>
              <div style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
                Rozkład score
              </div>
              <ScoreBreakdown components={sc} inputs={si} />
            </div>
          )}
          {(greenFlags.length > 0 || redFlags.length > 0) && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {greenFlags.length > 0 && (
                <div>
                  <div style={{ fontSize: 11, color: '#10b981', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>
                    Atuty
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                    {greenFlags.map((f, i) => (
                      <span key={i} style={{
                        background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.2)',
                        borderRadius: 4, padding: '2px 7px', fontSize: 11, color: '#10b981',
                      }}>{f}</span>
                    ))}
                  </div>
                </div>
              )}
              {redFlags.length > 0 && (
                <div>
                  <div style={{ fontSize: 11, color: '#f59e0b', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>
                    Ostrzeżenia
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                    {redFlags.map((f, i) => (
                      <span key={i} style={{
                        background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.2)',
                        borderRadius: 4, padding: '2px 7px', fontSize: 11, color: '#f59e0b',
                      }}>{f}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── StatCard ─────────────────────────────────────────────────────────────────

function StatCard({ label, value, sub, color }) {
  return (
    <div className="card" style={{ padding: '14px 18px' }}>
      <div style={{ fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8 }}>
        {label}
      </div>
      <div style={{ fontSize: 26, fontWeight: 700, color: color || 'var(--text)', fontFamily: 'JetBrains Mono, monospace', lineHeight: 1 }}>
        {value ?? '—'}
      </div>
      {sub && <div style={{ fontSize: 11, color: 'var(--text2)', marginTop: 6 }}>{sub}</div>}
    </div>
  );
}

// ─── Hunt page ────────────────────────────────────────────────────────────────

const SORT_OPTIONS = [
  { value: 'score', label: 'Score ↓' },
  { value: 'gap', label: 'RCN gap ↓' },
  { value: 'price', label: 'Cena ↑' },
  { value: 'price_per_m2', label: 'Cena/m² ↑' },
  { value: 'date', label: 'Najnowsze' },
];

export default function Hunt() {
  const [status, setStatus] = useState(null);
  const [listings, setListings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [hunting, setHunting] = useState(false);
  const [jobProgress, setJobProgress] = useState({ portals_counts: {} });
  const [jobMessage, setJobMessage] = useState('');
  const [sortBy, setSortBy] = useState('score');
  const [filterDirect, setFilterDirect] = useState(false);
  const [filterDistrict, setFilterDistrict] = useState('');
  const [minScore, setMinScore] = useState(null);
  const [alert, setAlert] = useState(null);
  const closeStreamRef = useRef(null);

  const fetchData = useCallback(async () => {
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
  }, [sortBy]);

  const fetchListings = useCallback(async () => {
    try {
      const res = await huntApi.results({
        limit: 100, sort_by: sortBy,
        direct_only: filterDirect || undefined,
        min_score: minScore || undefined,
        district: filterDistrict || undefined,
      });
      setListings(res.data.listings || []);
    } catch (e) { console.error(e); }
  }, [sortBy, filterDirect, minScore, filterDistrict]);

  useEffect(() => { fetchData(); return () => closeStreamRef.current?.(); }, []);
  useEffect(() => { fetchListings(); }, [sortBy, filterDirect, minScore, filterDistrict]);

  const handleStartHunt = async () => {
    if (hunting) return;
    setHunting(true);
    setJobProgress({ portals_counts: {} });
    setJobMessage('Uruchamiam...');
    setAlert(null);

    try {
      const res = await huntApi.start();
      const { job_id } = res.data;
      closeStreamRef.current?.();

      const close = createHuntStream(
        job_id,
        (event) => {
          if (event.message) setJobMessage(event.message);
          if (event.type === 'portal_done') {
            setJobProgress(prev => ({
              ...prev,
              portals_counts: { ...prev.portals_counts, [event.portal]: event.count },
            }));
          }
          if (event.type === 'ai_done' || event.type === 'enriching_done' || event.type === 'saving_done') {
            fetchListings();
          }
        },
        (doneEvent) => {
          setHunting(false);
          setJobMessage('');
          const msg = doneEvent.message || 'Polowanie zakończone.';
          setAlert({ type: doneEvent.type === 'error' ? 'error' : 'success', text: msg });
          fetchData();
          setTimeout(() => setAlert(null), 8000);
        },
        () => {
          setHunting(false);
          setJobMessage('');
          setAlert({ type: 'error', text: 'Błąd połączenia SSE.' });
        }
      );
      closeStreamRef.current = close;
    } catch (e) {
      setHunting(false);
      setJobMessage('');
      setAlert({ type: 'error', text: 'Błąd uruchomienia polowania.' });
    }
  };

  const opportunities = listings.filter(l => (l.score || 0) >= 0.25);
  const cfg = status?.config || {};

  const huntSummary = [
    cfg.max_price ? `do ${(cfg.max_price / 1000).toFixed(0)}k PLN` : null,
    cfg.max_area ? `do ${cfg.max_area} m²` : null,
    cfg.districts?.length ? cfg.districts.slice(0, 3).join(', ') : 'cała Warszawa',
  ].filter(Boolean).join(' · ');

  // Unikalne dzielnice z wyników
  const availableDistricts = [...new Set(listings.map(l => l.district).filter(Boolean))].sort();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 10 }}>
            <Target size={20} color="var(--accent)" />
            Centrum Polowania
          </h1>
          <p style={{ margin: '5px 0 0', color: 'var(--text2)', fontSize: 13 }}>
            {huntSummary || 'Skonfiguruj profil polowania'}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Link to="/hunt/settings" style={{ textDecoration: 'none' }}>
            <button className="btn btn-ghost" style={{ padding: '8px 14px', fontSize: 13 }}>
              <Settings size={14} /> Profil
            </button>
          </Link>
          <button
            className="btn btn-primary"
            onClick={handleStartHunt}
            disabled={hunting}
            style={{ minWidth: 148, fontSize: 13 }}
          >
            {hunting
              ? <><RefreshCw size={14} style={{ animation: 'spin 1s linear infinite' }} /> Polowanie...</>
              : <><Play size={14} /> Zacznij polowanie</>}
          </button>
        </div>
      </div>

      {/* Alert */}
      {alert && (
        <div style={{
          background: alert.type === 'success' ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
          border: `1px solid ${alert.type === 'success' ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'}`,
          borderRadius: 8, padding: '10px 14px', fontSize: 13,
          color: alert.type === 'success' ? '#10b981' : '#ef4444',
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          {alert.type === 'success' ? <Zap size={14} /> : <AlertCircle size={14} />}
          {alert.text}
        </div>
      )}

      {/* Progress */}
      {hunting && (
        <div className="card" style={{ padding: '12px 16px' }}>
          <div style={{ marginBottom: 8 }}>
            <div style={{ height: 2, background: 'rgba(255,255,255,0.06)', borderRadius: 1, overflow: 'hidden' }}>
              <div className="progress-animated" style={{ height: '100%', width: '100%' }} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            {Object.entries(jobProgress.portals_counts || {}).map(([portal, count]) => (
              <div key={portal} style={{
                background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.2)',
                borderRadius: 5, padding: '3px 9px', fontSize: 11, display: 'flex', gap: 5,
              }}>
                <span style={{ color: 'var(--muted)', textTransform: 'uppercase' }}>{portal}</span>
                <span style={{ color: '#10b981', fontFamily: 'JetBrains Mono, monospace', fontWeight: 600 }}>{count}</span>
              </div>
            ))}
            {jobMessage && (
              <span style={{ fontSize: 12, color: 'var(--text2)' }}>{jobMessage}</span>
            )}
          </div>
        </div>
      )}

      {/* Stats row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
        <StatCard label="W bazie" value={status?.total_listings ?? '—'} sub="wszystkich ofert" />
        <StatCard label="Okazje" value={status?.opportunities ?? opportunities.length} sub="score ≥ 25%" color="#10b981" />
        <StatCard label="Analiza AI" value={status?.pending_ai ?? '—'} sub="oczekuje" color="#f59e0b" />
        <StatCard
          label="RCN pokrycie"
          value={status?.rcn_district_coverage != null ? `${status.rcn_district_coverage}%` : '—'}
          sub={`${status?.rcn_transactions ?? '—'} transakcji`}
        />
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', padding: '10px 14px', background: 'var(--bg2)', borderRadius: 8, border: '1px solid var(--border)' }}>
        <Filter size={13} color="var(--muted)" />
        <span style={{ fontSize: 12, color: 'var(--muted)' }}>Sortuj:</span>
        {SORT_OPTIONS.map(opt => (
          <button key={opt.value} onClick={() => setSortBy(opt.value)} style={{
            padding: '4px 10px', borderRadius: 5, fontSize: 11, cursor: 'pointer', border: 'none',
            background: sortBy === opt.value ? 'var(--accent)' : 'var(--bg3)',
            color: sortBy === opt.value ? 'white' : 'var(--text2)',
            fontFamily: 'inherit', fontWeight: 500, transition: 'all 0.15s',
          }}>{opt.label}</button>
        ))}

        <div style={{ height: 16, width: 1, background: 'var(--border)', margin: '0 4px' }} />

        {availableDistricts.length > 0 && (
          <select
            value={filterDistrict}
            onChange={e => setFilterDistrict(e.target.value)}
            style={{
              background: 'var(--bg3)', border: '1px solid var(--border)', color: 'var(--text)',
              borderRadius: 5, padding: '4px 8px', fontSize: 11, fontFamily: 'inherit', outline: 'none',
            }}
          >
            <option value="">Wszystkie dzielnice</option>
            {availableDistricts.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        )}

        <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, cursor: 'pointer', color: 'var(--text2)' }}>
          <input type="checkbox" checked={filterDirect} onChange={e => setFilterDirect(e.target.checked)} style={{ accentColor: 'var(--accent)' }} />
          Bezpośrednie
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, cursor: 'pointer', color: 'var(--text2)' }}>
          <input type="checkbox" checked={minScore === 0.25} onChange={e => setMinScore(e.target.checked ? 0.25 : null)} style={{ accentColor: 'var(--accent)' }} />
          Tylko okazje
        </label>

        <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--muted)' }}>
          {listings.length} ofert · {opportunities.length} okazji
        </span>
      </div>

      {/* Listings */}
      {loading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[1, 2, 3].map(i => <div key={i} className="card" style={{ height: 140 }} />)}
        </div>
      ) : listings.length === 0 ? (
        <div className="card" style={{ padding: 56, textAlign: 'center' }}>
          <Target size={36} color="var(--muted)" style={{ opacity: 0.25, marginBottom: 14 }} />
          <div style={{ color: 'var(--text2)', marginBottom: 6 }}>Brak ofert spełniających kryteria</div>
          <div style={{ fontSize: 12, color: 'var(--muted)' }}>
            Uruchom polowanie lub dostosuj parametry w konfiguracji.
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {listings.map(l => <ListingCard key={l.id} listing={l} />)}
        </div>
      )}

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}