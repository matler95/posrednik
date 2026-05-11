export function ScoreBar({ score = 0, height = 4, showLabel = false }) {
  const pct = Math.round(score * 100);
  const color = score >= 0.5 ? '#10b981' : score >= 0.25 ? '#f59e0b' : '#5b6882';

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div className="score-bar" style={{ flex: 1, height }}>
        <div style={{
          width: `${pct}%`,
          height: '100%',
          background: color,
          borderRadius: 2,
          transition: 'width 0.5s ease',
        }} />
      </div>
      {showLabel && (
        <span className="mono" style={{ fontSize: 12, color, minWidth: 36, textAlign: 'right' }}>
          {pct}%
        </span>
      )}
    </div>
  );
}