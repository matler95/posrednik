import { clsx } from 'clsx';

export function ScoreBar({ score, className }) {
  // Score is 0.0 to 1.0
  const percentage = Math.round(score * 100);
  
  const getColor = (s) => {
    if (s >= 0.7) return 'bg-emerald-500 shadow-emerald-500/50';
    if (s >= 0.4) return 'bg-amber-500 shadow-amber-500/50';
    return 'bg-slate-500 shadow-slate-500/50';
  };

  return (
    <div className={clsx("w-full h-2 bg-slate-700 rounded-full overflow-hidden", className)}>
      <div 
        className={clsx("h-full rounded-full transition-all duration-500 shadow-sm", getColor(score))}
        style={{ width: `${percentage}%` }}
      />
    </div>
  );
}
