import { Link } from 'react-router-dom';
import { ScoreBar } from './ScoreBar';
import { MapPin, Maximize, Layers, ExternalLink, MessageSquare } from 'lucide-react';

export function ListingCard({ listing }) {
  const {
    id, title, price, area, district, rooms, 
    score, transaction_gap, images, direct_offer,
    rcn_benchmark
  } = listing;

  const pricePerM2 = Math.round(price / area);
  const gapPercent = transaction_gap ? Math.round(transaction_gap * 100) : null;
  const image = images?.[0] || 'https://images.unsplash.com/photo-1560518883-ce09059eeffa?ixlib=rb-4.0.3&auto=format&fit=crop&w=400&q=80';

  return (
    <div className="card-premium flex flex-col md:flex-row gap-6 group">
      {/* Thumbnail */}
      <div className="relative w-full md:w-64 h-48 rounded-xl overflow-hidden shrink-0">
        <img 
          src={image} 
          alt={title} 
          className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110" 
        />
        {direct_offer && (
          <div className="absolute top-3 left-3 bg-emerald-500 text-white text-[10px] font-bold px-2 py-1 rounded shadow-lg">
            BEZPOŚREDNIO
          </div>
        )}
        <div className="absolute bottom-3 right-3 bg-black/60 backdrop-blur-md text-white text-xs px-2 py-1 rounded-md border border-white/20">
          {images?.length || 0} zdjęć
        </div>
      </div>

      {/* Content */}
      <div className="flex-grow flex flex-col justify-between py-1">
        <div>
          <div className="flex justify-between items-start mb-2">
            <div>
               <h3 className="text-lg font-bold text-white line-clamp-1 group-hover:text-premium-accent transition-colors">
                 {title}
               </h3>
               <div className="flex items-center gap-4 mt-1 text-premium-muted text-sm">
                 <span className="flex items-center gap-1"><MapPin className="w-3.5 h-3.5" /> {district}</span>
                 <span className="flex items-center gap-1"><Maximize className="w-3.5 h-3.5" /> {area} m²</span>
                 <span className="flex items-center gap-1"><Layers className="w-3.5 h-3.5" /> {rooms} pok.</span>
               </div>
            </div>
            <div className="text-right">
              <div className="text-xl font-black text-white">{price?.toLocaleString()} PLN</div>
              <div className="text-xs text-premium-muted">{pricePerM2.toLocaleString()} PLN/m²</div>
            </div>
          </div>

          {/* AI Comment Snippet (if available) */}
          <div className="bg-slate-800/50 rounded-xl p-3 mb-4 border border-slate-700/30 flex gap-3 items-start">
             <MessageSquare className="w-4 h-4 text-premium-accent shrink-0 mt-0.5" />
             <p className="text-xs text-slate-300 italic line-clamp-2">
               {listing.llm_analysis?.summary || "Analiza AI w toku..."}
             </p>
          </div>
        </div>

        <div className="flex items-center justify-between gap-6">
          <div className="flex-grow">
            <div className="flex justify-between text-[10px] uppercase tracking-wider font-bold mb-1.5">
              <span className="text-premium-muted">Okazja Score</span>
              <span className={score >= 0.7 ? "text-emerald-400" : "text-amber-400"}>{Math.round(score * 100)}%</span>
            </div>
            <ScoreBar score={score} />
          </div>

          <div className="flex items-center gap-2 shrink-0">
             {gapPercent !== null && (
               <div className={cn(
                 "px-3 py-1.5 rounded-lg text-xs font-bold border",
                 gapPercent > 0 ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : "bg-red-500/10 text-red-400 border-red-500/20"
               )}>
                 {gapPercent > 0 ? '-' : '+'}{Math.abs(gapPercent)}% vs RCN
               </div>
             )}
             <Link 
               to={`/listings/${id}`}
               className="p-2.5 bg-slate-800 hover:bg-slate-700 text-white rounded-xl border border-slate-700 transition-colors"
             >
               <ExternalLink className="w-4 h-4" />
             </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

function cn(...inputs) {
  // Simple cn for this component if needed
  return inputs.filter(Boolean).join(' ');
}
