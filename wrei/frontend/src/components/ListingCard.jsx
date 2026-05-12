import { Link } from 'react-router-dom';
import { ScoreBar } from './ScoreBar';
import { MapPin, Maximize2, Hash, ExternalLink, Zap, TrendingDown, TrendingUp, User, Building } from 'lucide-react';

function fmt(n) {
  if (!n) return '—';
  return n.toLocaleString('pl-PL');
}

function ScoreBadge({ score }) {
  const pct = Math.round((score || 0) * 100);
  const bg = score >= 0.5 ? 'rgba(16,185,129,0.1)' : score >= 0.25 ? 'rgba(245,158,11,0.1)' : 'rgba(91,104,130,0.1)';
  const color = score >= 0.5 ? '#10b981' : score >= 0.25 ? '#f59e0b' : '#5b6882';
  const border = score >= 0.5 ? 'rgba(16,185,129,0.3)' : score >= 0.25 ? 'rgba(245,158,11,0.3)' : 'rgba(91,104,130,0.2)';
  return (
    <div style={{
      background: bg, border: `1px solid ${border}`,
      borderRadius: 8, padding: '6px 12px',
      display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: 64,
    }}>
      <span style={{ fontSize: 20, fontWeight: 700, color, fontFamily: 'JetBrains Mono, monospace', lineHeight: 1 }}>{pct}</span>
      <span style={{ fontSize: 9, color: 'var(--muted)', letterSpacing: '0.08em', textTransform: 'uppercase', marginTop: 2 }}>score</span>
    </div>
  );
}

export function ListingCard({ listing, compact = false }) {
  const {
    id, title, price, area, district, rooms,
    score, transaction_gap, images, direct_offer,
    rcn_benchmark, price_per_m2, llm_analysis, portal,
    days_on_market, condition, photo_analysis,
  } = listing;

  const img = Array.isArray(images) && images.length > 0
    ? (typeof images[0] === 'string' ? images[0] : images[0]?.url)
    : null;

  const gap = transaction_gap != null ? transaction_gap : null;
  const gapPct = gap != null ? Math.abs(Math.round(gap * 100)) : null;
  const gapPos = gap != null && gap > 0;
  const psm = price_per_m2 || (price && area ? Math.round(price / area) : null);

  const aiSummary = llm_analysis?.summary;
  const greenFlags = llm_analysis?.green_flags || [];
  const redFlags = llm_analysis?.red_flags || [];
  
  const photoCond = photo_analysis?.condition;

  return (
    <div className="card fade-in" style={{ padding: 0, overflow: 'hidden', display: 'flex' }}>
      {/* Image */}
      <div style={{
        width: compact ? 140 : 200,
        flexShrink: 0,
        background: 'var(--bg3)',
        position: 'relative',
        overflow: 'hidden',
      }}>
        {img ? (
          <img src={img} alt={title} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        ) : (
          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Building size={32} color="var(--muted)" style={{ opacity: 0.4 }} />
          </div>
        )}
        {direct_offer && (
          <div style={{
            position: 'absolute', top: 8, left: 8,
            background: '#10b981', color: 'white',
            fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
            textTransform: 'uppercase', padding: '2px 6px', borderRadius: 4,
          }}>
            <User size={9} style={{ display: 'inline', marginRight: 3 }} />
            Bezpośrednia
          </div>
        )}
        {days_on_market === 0 && (
          <div style={{
            position: 'absolute', bottom: 8, left: 8,
            background: 'rgba(59,130,246,0.9)', color: 'white',
            fontSize: 9, fontWeight: 700, letterSpacing: '0.06em',
            textTransform: 'uppercase', padding: '2px 6px', borderRadius: 4,
          }}>Nowe</div>
        )}
      </div>

      {/* Content */}
      <div style={{ flex: 1, padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>
        {/* Header row */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text)', lineHeight: 1.3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {title || 'Bez tytułu'}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 5, flexWrap: 'wrap' }}>
              {district && (
                <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--text2)' }}>
                  <MapPin size={11} />
                  {district}
                </span>
              )}
              {area && (
                <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--text2)' }}>
                  <Maximize2 size={11} />
                  {area} m²
                </span>
              )}
              {rooms && (
                <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--text2)' }}>
                  <Hash size={11} />
                  {rooms} pok.
                </span>
              )}
              {portal && (
                <span style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{portal}</span>
              )}
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, flexShrink: 0 }}>
            {/* Price */}
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text)' }}>
                {fmt(price)} <span style={{ fontSize: 12, fontWeight: 400, color: 'var(--muted)' }}>PLN</span>
              </div>
              {psm && (
                <div className="mono" style={{ fontSize: 11, color: 'var(--text2)', marginTop: 2 }}>
                  {fmt(psm)} zł/m²
                </div>
              )}
            </div>
            <ScoreBadge score={score} />
          </div>
        </div>

        {/* Score bar */}
        <ScoreBar score={score} showLabel={false} />

        {/* Metrics row */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {/* RCN gap */}
          {gap != null && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 5,
              background: gapPos ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)',
              border: `1px solid ${gapPos ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'}`,
              borderRadius: 6, padding: '4px 10px', fontSize: 12,
            }}>
              {gapPos ? <TrendingDown size={12} color="#10b981" /> : <TrendingUp size={12} color="#ef4444" />}
              <span style={{ color: gapPos ? '#10b981' : '#ef4444', fontWeight: 600 }}>
                {gapPos ? '-' : '+'}{gapPct}% vs RCN
              </span>
            </div>
          )}

          {/* RCN benchmark */}
          {rcn_benchmark && (
            <div style={{
              background: 'rgba(255,255,255,0.04)', borderRadius: 6, padding: '4px 10px',
              fontSize: 12, color: 'var(--text2)',
            }}>
              Benchmark: <span className="mono" style={{ color: 'var(--text)' }}>{fmt(Math.round(rcn_benchmark))} zł/m²</span>
            </div>
          )}

          {/* Condition */}
          {(condition || photoCond) && (
            <div style={{ display: 'flex', gap: 4 }}>
              {condition && (
                <div style={{
                  background: 'rgba(255,255,255,0.04)', borderRadius: 6, padding: '4px 10px',
                  fontSize: 11, color: 'var(--text2)', textTransform: 'capitalize', letterSpacing: '0.04em',
                }}>
                  {condition}
                </div>
              )}
              {photoCond && (
                <div style={{
                  background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.2)',
                  borderRadius: 6, padding: '4px 10px',
                  fontSize: 11, color: '#818cf8', textTransform: 'uppercase', fontWeight: 700,
                }} title="Ocena wizualna AI">
                  👁 {photoCond.replace('_', ' ')}
                </div>
              )}
            </div>
          )}
        </div>

        {/* AI Summary */}
        {aiSummary && (
          <div style={{
            background: 'rgba(59,130,246,0.05)',
            border: '1px solid rgba(59,130,246,0.1)',
            borderRadius: 8, padding: '10px 14px',
            display: 'flex', gap: 10, alignItems: 'flex-start',
          }}>
            <Zap size={13} color="var(--accent)" style={{ flexShrink: 0, marginTop: 2 }} />
            <p style={{ margin: 0, fontSize: 12, color: 'var(--text2)', lineHeight: 1.6 }}>
              {aiSummary}
            </p>
          </div>
        )}

        {/* Actions */}
        <div style={{ display: 'flex', gap: 8, marginTop: 'auto', paddingTop: 4 }}>
          <Link to={`/listings/${id}`} style={{ textDecoration: 'none' }}>
            <button className="btn btn-primary" style={{ padding: '7px 16px', fontSize: 13 }}>
              Szczegóły
            </button>
          </Link>
          {listing.url && (
            <a href={listing.url} target="_blank" rel="noreferrer" style={{ textDecoration: 'none' }}>
              <button className="btn btn-ghost" style={{ padding: '7px 14px', fontSize: 13 }}>
                <ExternalLink size={13} />
                Ogłoszenie
              </button>
            </a>
          )}
        </div>
      </div>
    </div>
  );
}