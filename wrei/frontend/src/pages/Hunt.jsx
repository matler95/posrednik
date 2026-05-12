import { useState, useEffect, useRef, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { huntApi, createHuntStream } from '../api/client';
import {
  Target, Play, RefreshCw, Settings, Filter, ExternalLink,
  TrendingDown, TrendingUp, Zap, AlertCircle, User, Building,
  ChevronDown, ChevronUp, MapPin, Maximize2, Hash, Info,
  Clock, BarChart2, CheckCircle, XCircle, Layers,
} from 'lucide-react';

// ─── helpers ─────────────────────────────────────────────────────────────────

function fmt(n, decimals = 0) {
  if (n == null || isNaN(n)) return '—';
  return Number(n).toLocaleString('pl-PL', { maximumFractionDigits: decimals });
}

function fmtK(n) {
  if (n == null || isNaN(n)) return '—';
  if (Math.abs(n) >= 1000) return `${(n / 1000).toFixed(0)}k`;
  return String(Math.round(n));
}

function scoreColor(s) {
  if (s >= 0.5) return '#10b981';
  if (s >= 0.3) return '#f59e0b';
  if (s >= 0.15) return '#60a5fa';
  return '#4b5563';
}

function scoreLabel(s) {
  if (s >= 0.5) return 'Okazja';
  if (s >= 0.3) return 'Dobra';
  if (s >= 0.15) return 'Średnia';
  return 'Słaba';
}

// ─── ScorePill ────────────────────────────────────────────────────────────────

function ScorePill({ score }) {
  const pct = Math.round((score || 0) * 100);
  const color = scoreColor(score || 0);
  const label = scoreLabel(score || 0);
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      background: `${color}15`, border: `1px solid ${color}40`,
      borderRadius: 10, padding: '8px 14px', minWidth: 62, flexShrink: 0,
      position: 'relative',
    }}>
      <span style={{
        fontSize: 22, fontWeight: 700, color,
        fontFamily: 'JetBrains Mono, monospace', lineHeight: 1,
      }}>
        {pct}
      </span>
      <span style={{
        fontSize: 9, color, opacity: 0.8,
        letterSpacing: '0.08em', textTransform: 'uppercase', marginTop: 3,
        fontWeight: 600,
      }}>
        {label}
      </span>
    </div>
  );
}

// ─── ScoreBreakdown ───────────────────────────────────────────────────────────

function ScoreBreakdown({ components, inputs }) {
  if (!components) return null;
  const bars = [
    { key: 'price_gap', label: 'ML estymata', max: 0.35, tip: 'ML vs cena oferty' },
    { key: 'txn_gap', label: 'Luka RCN', max: 0.30, tip: 'Realne transakcje vs cena' },
    { key: 'market_pos', label: 'Pozycja rynk.', max: 0.15, tip: 'Vs bieżące oferty' },
    { key: 'freshness', label: 'Świeżość', max: 0.12, tip: 'Czas od dodania' },
    { key: 'direct', label: 'Bezpośrednia', max: 0.08, tip: 'Bez pośrednika' },
    { key: 'text_boost', label: 'Analiza AI', max: 0.08, tip: 'Boost z LLM' },
    { key: 'photo_boost', label: 'Zdjęcia AI', max: 0.05, tip: 'Boost z Vision' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      {bars.map(({ key, label, max, tip }) => {
        const val = components[key] || 0;
        const pct = Math.min(100, Math.round((val / max) * 100));
        const color = pct >= 70 ? '#10b981' : pct >= 35 ? '#f59e0b' : '#4b5563';
        return (
          <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 8 }} title={tip}>
            <span style={{ fontSize: 10, color: 'var(--muted)', minWidth: 80, textAlign: 'right' }}>
              {label}
            </span>
            <div style={{
              flex: 1, height: 4, background: 'rgba(255,255,255,0.06)',
              borderRadius: 2, overflow: 'hidden',
            }}>
              <div style={{
                width: `${pct}%`, height: '100%', background: color,
                borderRadius: 2, transition: 'width 0.6s ease',
              }} />
            </div>
            <span style={{
              fontSize: 10, color, fontFamily: 'JetBrains Mono, monospace',
              minWidth: 36, textAlign: 'right',
            }}>
              {(val * 100).toFixed(1)}%
            </span>
          </div>
        );
      })}
      {inputs?.rcn_fallback && (
        <div style={{
          fontSize: 10, color: '#f59e0b', marginTop: 4,
          padding: '4px 8px', background: 'rgba(245,158,11,0.08)',
          borderRadius: 4, border: '1px solid rgba(245,158,11,0.2)',
        }}>
          ⚠ Benchmark z market_stats — brak danych RCN dla tej dzielnicy
        </div>
      )}
      {inputs?.estimated_savings_pln != null && inputs.estimated_savings_pln > 0 && (
        <div style={{
          fontSize: 11, color: '#10b981', marginTop: 4,
          padding: '5px 10px', background: 'rgba(16,185,129,0.08)',
          borderRadius: 4, border: '1px solid rgba(16,185,129,0.2)',
          fontWeight: 600,
        }}>
          💰 Szacowana oszczędność vs benchmark: {fmt(inputs.estimated_savings_pln)} PLN
        </div>
      )}
      {inputs && (
        <div style={{
          display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 4,
        }}>
          {inputs.price_per_m2 && (
            <span style={{ fontSize: 10, color: 'var(--muted)' }}>
              Cena/m²: <span style={{ color: 'var(--text2)' }}>{fmt(Math.round(inputs.price_per_m2))}</span>
            </span>
          )}
          {inputs.rcn_benchmark && (
            <span style={{ fontSize: 10, color: 'var(--muted)' }}>
              RCN: <span style={{ color: 'var(--text2)' }}>{fmt(Math.round(inputs.rcn_benchmark))}</span>
            </span>
          )}
          {inputs.condition_mult && inputs.condition_mult < 1 && (
            <span style={{ fontSize: 10, color: '#f59e0b' }}>
              Stan: ×{inputs.condition_mult}
            </span>
          )}
          {inputs.cagr_pct != null && (
            <span style={{ fontSize: 10, color: inputs.cagr_pct >= 0 ? '#10b981' : '#ef4444' }}>
              CAGR 5Y: {inputs.cagr_pct >= 0 ? '+' : ''}{inputs.cagr_pct}%
            </span>
          )}
        </div>
      )}
    </div>
  );
}

// ─── AIFlags ──────────────────────────────────────────────────────────────────

function AIFlags({ greenFlags = [], redFlags = [], urgency = [] }) {
  if (!greenFlags.length && !redFlags.length && !urgency.length) return null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {urgency.length > 0 && (
        <div>
          <div style={{
            fontSize: 10, color: '#60a5fa',
            textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 5,
            fontWeight: 700,
          }}>
            ⚡ Pilność
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {urgency.map((f, i) => (
              <span key={i} style={{
                background: 'rgba(96,165,250,0.1)',
                border: '1px solid rgba(96,165,250,0.25)',
                borderRadius: 4, padding: '2px 8px',
                fontSize: 11, color: '#60a5fa',
              }}>{f}</span>
            ))}
          </div>
        </div>
      )}
      {greenFlags.length > 0 && (
        <div>
          <div style={{
            fontSize: 10, color: '#10b981',
            textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 5,
            fontWeight: 700,
          }}>
            ✓ Atuty
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {greenFlags.map((f, i) => (
              <span key={i} style={{
                background: 'rgba(16,185,129,0.08)',
                border: '1px solid rgba(16,185,129,0.2)',
                borderRadius: 4, padding: '2px 8px',
                fontSize: 11, color: '#10b981',
              }}>{f}</span>
            ))}
          </div>
        </div>
      )}
      {redFlags.length > 0 && (
        <div>
          <div style={{
            fontSize: 10, color: '#f59e0b',
            textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 5,
            fontWeight: 700,
          }}>
            ⚠ Ostrzeżenia
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {redFlags.map((f, i) => (
              <span key={i} style={{
                background: 'rgba(245,158,11,0.08)',
                border: '1px solid rgba(245,158,11,0.2)',
                borderRadius: 4, padding: '2px 8px',
                fontSize: 11, color: '#f59e0b',
              }}>{f}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── ListingCard ──────────────────────────────────────────────────────────────

function ListingCard({ listing, aiUpdates }) {
  const [expanded, setExpanded] = useState(false);

  const {
    id, title, price, area, district, rooms,
    score, score_components, transaction_gap, images, direct_offer,
    rcn_benchmark, price_per_m2, llm_analysis, portal,
    days_on_market, condition, cagr_5y, estimated_value,
  } = listing;

  // Merge live AI updates (ze SSE stream)
  const ai = aiUpdates?.[id] ? { ...llm_analysis, ...aiUpdates[id] } : llm_analysis;

  const img = Array.isArray(images) && images.length > 0
    ? (typeof images[0] === 'string' ? images[0] : images[0]?.url)
    : null;

  const gap = transaction_gap != null ? transaction_gap : null;
  const gapPct = gap != null ? Math.abs(Math.round(gap * 100)) : null;
  const gapPos = gap != null && gap > 0;
  const psm = price_per_m2 || (price && area ? Math.round(price / area) : null);

  const sc = score_components?.components;
  const si = score_components?.inputs;
  const savings = si?.estimated_savings_pln;

  const greenFlags = ai?.green_flags || [];
  const redFlags = ai?.red_flags || [];
  const urgency = ai?.urgency_signals || [];
  const aiSummary = ai?.summary;
  const investScore = ai?.investment_score;
  const negoPotential = ai?.negotiation_potential;
  const hasAI = !!(aiSummary || greenFlags.length || redFlags.length);
  const aiPending = !hasAI && !ai?.error;

  const hasExpand = !!(sc || greenFlags.length || redFlags.length || urgency.length);

  return (
    <div
      className="card fade-in"
      style={{
        padding: 0, overflow: 'hidden',
        borderLeft: score >= 0.5
          ? '3px solid #10b981'
          : score >= 0.3
            ? '3px solid #f59e0b'
            : '3px solid transparent',
        transition: 'border-color 0.3s',
      }}
    >
      <div style={{ display: 'flex' }}>
        {/* Thumbnail */}
        <div style={{
          width: 190, flexShrink: 0, background: 'var(--bg3)',
          position: 'relative', minHeight: 150,
        }}>
          {img ? (
            <img
              src={img} alt={title}
              style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block', minHeight: 150 }}
              loading="lazy"
            />
          ) : (
            <div style={{ height: 150, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Building size={28} color="var(--muted)" style={{ opacity: 0.25 }} />
            </div>
          )}
          {/* Badges */}
          {direct_offer && (
            <div style={{
              position: 'absolute', top: 8, left: 8,
              background: '#10b981', color: '#fff',
              fontSize: 9, fontWeight: 700, padding: '2px 6px',
              borderRadius: 4, letterSpacing: '0.08em', textTransform: 'uppercase',
              display: 'flex', alignItems: 'center', gap: 3,
            }}>
              <User size={9} /> Bezpośrednia
            </div>
          )}
          {days_on_market === 0 && (
            <div style={{
              position: 'absolute', bottom: 8, left: 8,
              background: 'rgba(59,130,246,0.9)', color: '#fff',
              fontSize: 9, fontWeight: 700, padding: '2px 6px', borderRadius: 4,
            }}>
              Nowe
            </div>
          )}
          {days_on_market > 0 && days_on_market <= 3 && (
            <div style={{
              position: 'absolute', bottom: 8, left: 8,
              background: 'rgba(96,165,250,0.8)', color: '#fff',
              fontSize: 9, fontWeight: 600, padding: '2px 6px', borderRadius: 4,
            }}>
              {days_on_market}d
            </div>
          )}
          {/* Portal badge */}
          {portal && (
            <div style={{
              position: 'absolute', top: 8, right: 8,
              background: 'rgba(0,0,0,0.65)', color: 'rgba(255,255,255,0.7)',
              fontSize: 9, fontWeight: 700, padding: '2px 5px',
              borderRadius: 3, letterSpacing: '0.08em', textTransform: 'uppercase',
            }}>
              {portal}
            </div>
          )}
        </div>

        {/* Main content */}
        <div style={{
          flex: 1, padding: '14px 18px',
          display: 'flex', flexDirection: 'column', gap: 9, minWidth: 0,
        }}>
          {/* Header row */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{
                fontSize: 15, fontWeight: 600, color: 'var(--text)',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                lineHeight: 1.3,
              }}>
                {title || 'Bez tytułu'}
              </div>
              <div style={{ display: 'flex', gap: 10, marginTop: 5, flexWrap: 'wrap', alignItems: 'center' }}>
                {district && (
                  <span style={{ fontSize: 12, color: 'var(--text2)', display: 'flex', alignItems: 'center', gap: 3 }}>
                    <MapPin size={11} color="var(--accent)" />{district}
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
                {condition && (
                  <span style={{
                    fontSize: 10, color: 'var(--muted)',
                    background: 'rgba(255,255,255,0.05)',
                    padding: '1px 6px', borderRadius: 3,
                    textTransform: 'capitalize',
                  }}>
                    {condition}
                  </span>
                )}
              </div>
            </div>

            {/* Price + Score */}
            <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', flexShrink: 0 }}>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text)', lineHeight: 1 }}>
                  {fmt(price)}
                  <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--muted)', marginLeft: 4 }}>PLN</span>
                </div>
                {psm && (
                  <div style={{
                    fontSize: 11, color: 'var(--text2)', marginTop: 3,
                    fontFamily: 'JetBrains Mono, monospace',
                  }}>
                    {fmt(psm)} zł/m²
                  </div>
                )}
                {estimated_value && estimated_value > 0 && (
                  <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 2 }}>
                    est. {fmtK(estimated_value)} PLN
                  </div>
                )}
              </div>
              <ScorePill score={score} />
            </div>
          </div>

          {/* Metrics row */}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
            {/* RCN gap */}
            {gap != null && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 5,
                background: gapPos ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)',
                border: `1px solid ${gapPos ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)'}`,
                borderRadius: 6, padding: '4px 10px', fontSize: 12,
              }}>
                {gapPos
                  ? <TrendingDown size={12} color="#10b981" />
                  : <TrendingUp size={12} color="#ef4444" />}
                <span style={{ color: gapPos ? '#10b981' : '#ef4444', fontWeight: 600 }}>
                  {gapPos ? '-' : '+'}{gapPct}% vs RCN
                </span>
              </div>
            )}

            {/* Savings */}
            {savings != null && savings > 0 && (
              <div style={{
                background: 'rgba(16,185,129,0.08)',
                border: '1px solid rgba(16,185,129,0.18)',
                borderRadius: 6, padding: '4px 10px',
                fontSize: 12, color: '#10b981', fontWeight: 600,
              }}>
                💰 {fmt(savings)} PLN
              </div>
            )}

            {/* RCN benchmark */}
            {rcn_benchmark && (
              <div style={{
                background: 'rgba(255,255,255,0.04)',
                borderRadius: 6, padding: '4px 10px',
                fontSize: 11, color: 'var(--text2)',
              }}>
                RCN: <span style={{ color: 'var(--text)', fontFamily: 'JetBrains Mono, monospace' }}>
                  {fmt(Math.round(rcn_benchmark))} zł/m²
                </span>
              </div>
            )}

            {/* AI investment score */}
            {investScore != null && (
              <div style={{
                background: 'rgba(96,165,250,0.08)',
                border: '1px solid rgba(96,165,250,0.2)',
                borderRadius: 6, padding: '4px 10px',
                fontSize: 11, color: '#60a5fa',
              }}>
                AI: <span style={{ fontWeight: 700 }}>{investScore}/10</span>
                {negoPotential != null && (
                  <span style={{ color: 'var(--muted)', marginLeft: 6 }}>
                    nego {negoPotential}/10
                  </span>
                )}
              </div>
            )}

            {/* CAGR */}
            {cagr_5y != null && (
              <div style={{
                background: 'rgba(255,255,255,0.04)',
                borderRadius: 6, padding: '4px 10px',
                fontSize: 11,
                color: cagr_5y >= 0 ? '#10b981' : '#ef4444',
              }}>
                CAGR 5Y: {cagr_5y >= 0 ? '+' : ''}{(cagr_5y * 100).toFixed(1)}%
              </div>
            )}

            {/* AI pending indicator */}
            {aiPending && (
              <div style={{
                background: 'rgba(255,255,255,0.03)',
                borderRadius: 6, padding: '4px 10px',
                fontSize: 11, color: 'var(--muted)',
                display: 'flex', alignItems: 'center', gap: 5,
              }}>
                <RefreshCw size={10} style={{ animation: 'spin 2s linear infinite' }} />
                Analiza AI...
              </div>
            )}
          </div>

          {/* AI Summary */}
          {aiSummary && (
            <div style={{
              background: 'rgba(59,130,246,0.05)',
              border: '1px solid rgba(59,130,246,0.12)',
              borderRadius: 7, padding: '9px 13px',
              display: 'flex', gap: 8, alignItems: 'flex-start',
            }}>
              <Zap size={12} color="var(--accent)" style={{ flexShrink: 0, marginTop: 2 }} />
              <p style={{ margin: 0, fontSize: 12, color: 'var(--text2)', lineHeight: 1.65 }}>
                {aiSummary}
              </p>
            </div>
          )}

          {/* Quick flags preview (when not expanded) */}
          {!expanded && (greenFlags.length > 0 || redFlags.length > 0) && (
            <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
              {greenFlags.slice(0, 2).map((f, i) => (
                <span key={i} style={{
                  fontSize: 10, color: '#10b981',
                  background: 'rgba(16,185,129,0.07)',
                  padding: '2px 7px', borderRadius: 3,
                  border: '1px solid rgba(16,185,129,0.15)',
                }}>✓ {f}</span>
              ))}
              {redFlags.slice(0, 2).map((f, i) => (
                <span key={i} style={{
                  fontSize: 10, color: '#f59e0b',
                  background: 'rgba(245,158,11,0.07)',
                  padding: '2px 7px', borderRadius: 3,
                  border: '1px solid rgba(245,158,11,0.15)',
                }}>⚠ {f}</span>
              ))}
              {(greenFlags.length + redFlags.length) > 4 && (
                <span style={{ fontSize: 10, color: 'var(--muted)', padding: '2px 0' }}>
                  +{greenFlags.length + redFlags.length - 4} więcej
                </span>
              )}
            </div>
          )}

          {/* Actions */}
          <div style={{ display: 'flex', gap: 7, alignItems: 'center', marginTop: 'auto', paddingTop: 2 }}>
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
            {hasExpand && (
              <button
                className="btn btn-ghost"
                style={{ padding: '6px 12px', fontSize: 12, marginLeft: 'auto' }}
                onClick={() => setExpanded(e => !e)}
              >
                {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                {expanded ? 'Zwiń' : 'Rozkład score'}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Expanded: score breakdown + AI flags */}
      {expanded && (
        <div style={{
          borderTop: '1px solid var(--border)',
          padding: '16px 18px',
          background: 'rgba(255,255,255,0.012)',
          display: 'grid',
          gridTemplateColumns: sc ? '1fr 1fr' : '1fr',
          gap: 24,
        }}>
          {sc && (
            <div>
              <div style={{
                fontSize: 10, color: 'var(--muted)',
                textTransform: 'uppercase', letterSpacing: '0.1em',
                marginBottom: 10, fontWeight: 700,
                display: 'flex', alignItems: 'center', gap: 5,
              }}>
                <BarChart2 size={11} /> Rozkład score
              </div>
              <ScoreBreakdown components={sc} inputs={si} />
            </div>
          )}
          {(greenFlags.length > 0 || redFlags.length > 0 || urgency.length > 0) && (
            <div>
              <div style={{
                fontSize: 10, color: 'var(--muted)',
                textTransform: 'uppercase', letterSpacing: '0.1em',
                marginBottom: 10, fontWeight: 700,
                display: 'flex', alignItems: 'center', gap: 5,
              }}>
                <Zap size={11} /> Analiza AI
              </div>
              <AIFlags greenFlags={greenFlags} redFlags={redFlags} urgency={urgency} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── StatCard ─────────────────────────────────────────────────────────────────

function StatCard({ label, value, sub, color, icon: Icon }) {
  return (
    <div className="card" style={{ padding: '14px 18px' }}>
      <div style={{
        fontSize: 10, color: 'var(--muted)',
        textTransform: 'uppercase', letterSpacing: '0.1em',
        marginBottom: 8, display: 'flex', alignItems: 'center', gap: 5,
      }}>
        {Icon && <Icon size={11} />}{label}
      </div>
      <div style={{
        fontSize: 26, fontWeight: 700,
        color: color || 'var(--text)',
        fontFamily: 'JetBrains Mono, monospace', lineHeight: 1,
      }}>
        {value ?? '—'}
      </div>
      {sub && (
        <div style={{ fontSize: 11, color: 'var(--text2)', marginTop: 6 }}>{sub}</div>
      )}
    </div>
  );
}

// ─── DataQualityBanner ────────────────────────────────────────────────────────

function DataQualityBanner({ status }) {
  const coverage = status?.rcn_district_coverage || 0;
  const rcnCount = status?.rcn_transactions || 0;
  if (coverage >= 65 && rcnCount > 500) return null;

  return (
    <div style={{
      background: coverage < 30 ? 'rgba(239,68,68,0.07)' : 'rgba(245,158,11,0.07)',
      border: `1px solid ${coverage < 30 ? 'rgba(239,68,68,0.2)' : 'rgba(245,158,11,0.2)'}`,
      borderRadius: 8, padding: '10px 14px',
      fontSize: 12,
      color: coverage < 30 ? '#ef4444' : '#f59e0b',
      display: 'flex', alignItems: 'center', gap: 8,
    }}>
      <Info size={13} style={{ flexShrink: 0 }} />
      <span>
        {rcnCount === 0
          ? 'Brak danych transakcyjnych RCN — scoring bazuje wyłącznie na cenach ofertowych. Importuj dane w zakładce Statystyki.'
          : `Pokrycie RCN: ${coverage}% dzielnic (${rcnCount} transakcji) — scoring może być mniej precyzyjny dla dzielnic bez danych.`}
      </span>
    </div>
  );
}

// ─── StickyBar ────────────────────────────────────────────────────────────────

function StickyBar({ listings, opportunities, aiAnalyzed, sortBy, setSortBy, filterDirect, setFilterDirect, minScore, setMinScore, filterDistrict, setFilterDistrict, availableDistricts }) {
  const SORT_OPTIONS = [
    { value: 'score', label: 'Score ↓' },
    { value: 'gap', label: 'RCN gap ↓' },
    { value: 'price', label: 'Cena ↑' },
    { value: 'price_per_m2', label: 'PLN/m² ↑' },
    { value: 'date', label: 'Najnowsze' },
  ];

  return (
    <div style={{
      position: 'sticky', top: 0, zIndex: 50,
      background: 'rgba(8, 12, 20, 0.94)',
      backdropFilter: 'blur(12px)',
      borderBottom: '1px solid var(--border)',
      padding: '10px 0',
      marginBottom: 4,
      display: 'flex', flexDirection: 'column', gap: 8,
    }}>
      {/* Summary */}
      <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 12, color: 'var(--text2)' }}>
          <span style={{ color: 'var(--text)', fontWeight: 600 }}>{listings.length}</span> ofert
          {' · '}
          <span style={{ color: '#10b981', fontWeight: 600 }}>{opportunities}</span> okazji
          {aiAnalyzed > 0 && (
            <>
              {' · '}
              <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{aiAnalyzed}</span> z AI
            </>
          )}
        </span>
        <div style={{ height: 14, width: 1, background: 'var(--border)' }} />
        <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', alignItems: 'center' }}>
          <Filter size={12} color="var(--muted)" />
          {SORT_OPTIONS.map(opt => (
            <button
              key={opt.value}
              onClick={() => setSortBy(opt.value)}
              style={{
                padding: '3px 9px', borderRadius: 5, fontSize: 11,
                cursor: 'pointer', border: 'none',
                background: sortBy === opt.value ? 'var(--accent)' : 'var(--bg3)',
                color: sortBy === opt.value ? 'white' : 'var(--text2)',
                fontFamily: 'inherit', fontWeight: 500, transition: 'all 0.15s',
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          {availableDistricts.length > 0 && (
            <select
              value={filterDistrict}
              onChange={e => setFilterDistrict(e.target.value)}
              style={{
                background: 'var(--bg3)', border: '1px solid var(--border)',
                color: filterDistrict ? 'var(--text)' : 'var(--muted)',
                borderRadius: 5, padding: '3px 8px', fontSize: 11,
                fontFamily: 'inherit', outline: 'none', cursor: 'pointer',
              }}
            >
              <option value="">Wszystkie dzielnice</option>
              {availableDistricts.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
          )}

          <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, cursor: 'pointer', color: 'var(--text2)' }}>
            <input
              type="checkbox" checked={filterDirect}
              onChange={e => setFilterDirect(e.target.checked)}
              style={{ accentColor: 'var(--accent)' }}
            />
            Bezpośrednie
          </label>

          <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, cursor: 'pointer', color: 'var(--text2)' }}>
            <input
              type="checkbox" checked={minScore === 0.25}
              onChange={e => setMinScore(e.target.checked ? 0.25 : null)}
              style={{ accentColor: 'var(--accent)' }}
            />
            Tylko okazje (≥25%)
          </label>
        </div>
      </div>
    </div>
  );
}

// ─── Main Hunt page ───────────────────────────────────────────────────────────

export default function Hunt() {
  const [status, setStatus] = useState(null);
  const [listings, setListings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [hunting, setHunting] = useState(false);
  const [jobProgress, setJobProgress] = useState({ portals_counts: {} });
  const [jobMessage, setJobMessage] = useState('');
  const [jobPhase, setJobPhase] = useState('');
  const [sortBy, setSortBy] = useState('score');
  const [filterDirect, setFilterDirect] = useState(false);
  const [filterDistrict, setFilterDistrict] = useState('');
  const [minScore, setMinScore] = useState(null);
  const [alert, setAlert] = useState(null);
  const [aiUpdates, setAiUpdates] = useState({});
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
      console.error('[Hunt] fetchData error:', e);
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
    } catch (e) {
      console.error('[Hunt] fetchListings error:', e);
    }
  }, [sortBy, filterDirect, minScore, filterDistrict]);

  useEffect(() => {
    fetchData();
    return () => closeStreamRef.current?.();
  }, []);

  useEffect(() => {
    if (!loading) fetchListings();
  }, [sortBy, filterDirect, minScore, filterDistrict]);

  const handleStartHunt = async () => {
    if (hunting) return;
    setHunting(true);
    setJobProgress({ portals_counts: {} });
    setJobMessage('Uruchamiam polowanie...');
    setJobPhase('scraping');
    setAlert(null);
    setAiUpdates({});

    try {
      const res = await huntApi.start();
      const { job_id } = res.data;
      closeStreamRef.current?.();

      const close = createHuntStream(
        job_id,
        (event) => {
          if (event.message) setJobMessage(event.message);
          if (event.status) setJobPhase(event.status);

          if (event.type === 'portal_done') {
            setJobProgress(prev => ({
              ...prev,
              portals_counts: { ...prev.portals_counts, [event.portal]: event.count },
            }));
          }

          // Live AI update — aktualizuj karty na bieżąco
          if (event.type === 'ai_done' && event.listing_id) {
            setAiUpdates(prev => ({
              ...prev,
              [event.listing_id]: {
                summary: event.summary,
                investment_score: event.investment_score,
                negotiation_potential: event.negotiation_potential,
                green_flags: event.green_flags || [],
                red_flags: event.red_flags || [],
              },
            }));
          }

          // Odśwież listę po ważnych fazach
          if (['saving_done', 'enriching_done'].includes(event.type)) {
            fetchListings();
          }
        },
        (doneEvent) => {
          setHunting(false);
          setJobMessage('');
          setJobPhase('');
          const msg = doneEvent.message || 'Polowanie zakończone.';
          setAlert({ type: doneEvent.type === 'error' ? 'error' : 'success', text: msg });
          fetchData();
          setTimeout(() => setAlert(null), 10000);
        },
        () => {
          setHunting(false);
          setJobMessage('');
          setJobPhase('');
          setAlert({ type: 'error', text: 'Utracono połączenie SSE. Odśwież stronę.' });
        }
      );
      closeStreamRef.current = close;
    } catch (e) {
      setHunting(false);
      setJobMessage('');
      setJobPhase('');
      setAlert({ type: 'error', text: 'Błąd uruchomienia polowania. Sprawdź połączenie z backendem.' });
    }
  };

  // Computed
  const opportunities = listings.filter(l => (l.score || 0) >= 0.25);
  const aiAnalyzed = listings.filter(l => l.llm_analysis?.summary).length;
  const cfg = status?.config || {};

  const huntSummary = [
    cfg.max_price ? `do ${(cfg.max_price / 1000).toFixed(0)}k PLN` : null,
    cfg.max_area ? `do ${cfg.max_area} m²` : null,
    cfg.districts?.length
      ? cfg.districts.slice(0, 3).join(', ') + (cfg.districts.length > 3 ? ` +${cfg.districts.length - 3}` : '')
      : 'cała Warszawa',
  ].filter(Boolean).join(' · ');

  const availableDistricts = [...new Set(listings.map(l => l.district).filter(Boolean))].sort();

  const phaseLabel = {
    running: '🔍 Skanowanie portali',
    enriching: '📊 Scoring i analiza RCN',
    saving: '💾 Zapis do bazy',
    ai_analysis: '🧠 Analiza AI',
    done: '✅ Gotowe',
    error: '❌ Błąd',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {/* Header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between',
        alignItems: 'flex-start', flexWrap: 'wrap', gap: 12,
      }}>
        <div>
          <h1 style={{
            margin: 0, fontSize: 22, fontWeight: 700,
            display: 'flex', alignItems: 'center', gap: 10,
          }}>
            <Target size={20} color="var(--accent)" />
            Centrum Polowania
          </h1>
          <p style={{ margin: '5px 0 0', color: 'var(--text2)', fontSize: 13 }}>
            {huntSummary || 'Skonfiguruj profil polowania w ustawieniach'}
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
            style={{ minWidth: 160, fontSize: 13 }}
          >
            {hunting
              ? <><RefreshCw size={14} style={{ animation: 'spin 1s linear infinite' }} /> Polowanie...</>
              : <><Play size={14} /> Zacznij polowanie</>}
          </button>
        </div>
      </div>

      {/* Data quality warning */}
      <DataQualityBanner status={status} />

      {/* Alert */}
      {alert && (
        <div style={{
          background: alert.type === 'success'
            ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)',
          border: `1px solid ${alert.type === 'success'
            ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)'}`,
          borderRadius: 8, padding: '10px 16px', fontSize: 13,
          color: alert.type === 'success' ? '#10b981' : '#ef4444',
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          {alert.type === 'success' ? <CheckCircle size={14} /> : <AlertCircle size={14} />}
          {alert.text}
        </div>
      )}

      {/* Job progress */}
      {hunting && (
        <div className="card" style={{ padding: '12px 16px' }}>
          {/* Phase indicator */}
          <div style={{
            display: 'flex', justifyContent: 'space-between', marginBottom: 8,
            alignItems: 'center',
          }}>
            <span style={{ fontSize: 12, color: 'var(--text2)', fontWeight: 500 }}>
              {phaseLabel[jobPhase] || jobMessage || 'Przetwarzanie...'}
            </span>
            <span style={{ fontSize: 10, color: 'var(--muted)' }}>
              {Object.values(jobProgress.portals_counts || {}).reduce((a, b) => a + b, 0)} ofert
            </span>
          </div>
          <div style={{ height: 2, background: 'rgba(255,255,255,0.06)', borderRadius: 1, overflow: 'hidden', marginBottom: 10 }}>
            <div className="progress-animated" style={{ height: '100%', width: '100%' }} />
          </div>
          {/* Portal counts */}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {Object.entries(jobProgress.portals_counts || {}).map(([portal, count]) => (
              <div key={portal} style={{
                background: 'rgba(16,185,129,0.08)',
                border: '1px solid rgba(16,185,129,0.18)',
                borderRadius: 5, padding: '3px 9px', fontSize: 11,
                display: 'flex', gap: 5,
              }}>
                <span style={{ color: 'var(--muted)', textTransform: 'uppercase' }}>{portal}</span>
                <span style={{ color: '#10b981', fontFamily: 'JetBrains Mono, monospace', fontWeight: 600 }}>
                  {count}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Stats row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
        <StatCard
          label="W bazie" icon={Layers}
          value={status?.total_listings ?? '—'}
          sub="wszystkich ofert"
        />
        <StatCard
          label="Okazje" icon={Target}
          value={status?.opportunities ?? opportunities.length}
          sub="score ≥ 25%"
          color="#10b981"
        />
        <StatCard
          label="Oczekuje AI" icon={Zap}
          value={status?.pending_ai ?? '—'}
          sub="w kolejce LLM"
          color="#f59e0b"
        />
        <StatCard
          label="Pokrycie RCN"
          value={status?.rcn_district_coverage != null
            ? `${status.rcn_district_coverage}%`
            : '—'}
          sub={`${status?.rcn_transactions ?? '—'} transakcji`}
          color={
            (status?.rcn_district_coverage || 0) >= 65 ? '#10b981'
              : (status?.rcn_district_coverage || 0) >= 30 ? '#f59e0b'
                : '#ef4444'
          }
        />
      </div>

      {/* Sticky filters bar */}
      <StickyBar
        listings={listings}
        opportunities={opportunities.length}
        aiAnalyzed={aiAnalyzed}
        sortBy={sortBy} setSortBy={setSortBy}
        filterDirect={filterDirect} setFilterDirect={setFilterDirect}
        minScore={minScore} setMinScore={setMinScore}
        filterDistrict={filterDistrict} setFilterDistrict={setFilterDistrict}
        availableDistricts={availableDistricts}
      />

      {/* Listings */}
      {loading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[1, 2, 3].map(i => (
            <div key={i} className="card" style={{ height: 160, opacity: 0.5 }} />
          ))}
        </div>
      ) : listings.length === 0 ? (
        <div className="card" style={{ padding: 56, textAlign: 'center' }}>
          <Target size={36} color="var(--muted)" style={{ opacity: 0.2, marginBottom: 16 }} />
          <div style={{ color: 'var(--text2)', marginBottom: 6, fontSize: 15 }}>
            Brak ofert spełniających kryteria
          </div>
          <div style={{ fontSize: 12, color: 'var(--muted)', maxWidth: 340, margin: '0 auto' }}>
            Uruchom polowanie przyciskiem powyżej lub dostosuj parametry w{' '}
            <Link to="/hunt/settings" style={{ color: 'var(--accent)', textDecoration: 'none' }}>
              konfiguracji profilu
            </Link>.
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {listings.map(l => (
            <ListingCard
              key={l.id}
              listing={l}
              aiUpdates={aiUpdates}
            />
          ))}
        </div>
      )}

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}