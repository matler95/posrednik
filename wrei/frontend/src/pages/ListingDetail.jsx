import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { listingApi } from '../api/client';
import { ScoreBar } from '../components/ScoreBar';
import {
  ArrowLeft, MapPin, Maximize, Layers, Calendar,
  Home, ExternalLink, CheckCircle2, AlertTriangle,
  Info, TrendingDown, Clock, TrendingUp
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export default function ListingDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [listing, setListing] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchDetail = async () => {
      try {
        const res = await listingApi.getDetail(id);
        setListing(res.data);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchDetail();
  }, [id]);

  if (loading) return <div className="animate-pulse space-y-8"><div className="h-64 card-premium" /><div className="h-96 card-premium" /></div>;
  if (!listing) return <div className="text-center py-20">Nie znaleziono oferty.</div>;

  const gapPercent = listing.transaction_gap ? Math.round(listing.transaction_gap * 100) : null;
  const pricePerM2 = Math.round(listing.price / listing.area);

  return (
    <div className="max-w-6xl mx-auto space-y-8 animate-in slide-in-from-bottom-4 duration-500">
      {/* Navigation */}
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-2 text-premium-muted hover:text-white transition-colors font-medium"
      >
        <ArrowLeft className="w-4 h-4" /> Powrót do listy
      </button>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column: Visuals & Core Info */}
        <div className="lg:col-span-2 space-y-8">
          <div className="card-premium p-0 overflow-hidden">
            <div className="relative h-96 group">
              <img
                src={listing.images?.[0] || 'https://images.unsplash.com/photo-1560518883-ce09059eeffa'}
                className="w-full h-full object-cover"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent"></div>
              <div className="absolute bottom-6 left-6 right-6 flex justify-between items-end">
                <div>
                  <h1 className="text-3xl font-black text-white">{listing.title}</h1>
                  <div className="flex items-center gap-2 text-slate-300 mt-2">
                    <MapPin className="w-4 h-4 text-premium-accent" /> {listing.district}, Warszawa
                  </div>
                </div>
                <a
                  href={listing.url}
                  target="_blank"
                  rel="noreferrer"
                  className="bg-white/10 hover:bg-white/20 backdrop-blur-md text-white px-4 py-2 rounded-xl border border-white/20 flex items-center gap-2 transition-all"
                >
                  <ExternalLink className="w-4 h-4" /> Otwórz oryginał
                </a>
              </div>
            </div>
          </div>

          {/* AI Analysis Section */}
          <div className="card-premium">
            <h2 className="text-xl font-bold text-white mb-6 flex items-center gap-2">
              <Info className="w-5 h-5 text-premium-accent" /> Analiza Inteligentna (Qwen 2.5)
            </h2>

            <div className="space-y-6">
              <div className="bg-slate-800/40 rounded-2xl p-6 border border-slate-700/50">
                <p className="text-slate-200 leading-relaxed italic">
                  "{listing.llm_analysis?.summary || "Analiza AI jest generowana w tle. Odśwież za chwilę, aby zobaczyć szczegóły."}"
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="flex items-start gap-3 p-4 bg-emerald-500/5 rounded-xl border border-emerald-500/10">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
                  <div>
                    <div className="text-sm font-bold text-emerald-400">Atuty</div>
                    <p className="text-xs text-slate-400 mt-1">{(listing.llm_analysis?.green_flags || []).join(', ') || 'Analiza w toku...'}</p>
                  </div>
                </div>
                <div className="flex items-start gap-3 p-4 bg-amber-500/5 rounded-xl border border-amber-500/10">
                  <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
                  <div>
                    <div className="text-sm font-bold text-amber-400">Ryzyka</div>
                    <p className="text-xs text-slate-400 mt-1">{(listing.llm_analysis?.red_flags || []).join(', ') || 'Analiza w toku...'}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Detailed Parameters */}
          <div className="card-premium">
            <h2 className="text-xl font-bold text-white mb-6">Parametry Mieszkania</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
              <ParamItem icon={Maximize} label="Powierzchnia" value={`${listing.area} m²`} />
              <ParamItem icon={Layers} label="Pokoje" value={listing.rooms} />
              <ParamItem icon={Clock} label="Rok budowy" value={listing.year_built || 'Brak danych'} />
              <ParamItem icon={Home} label="Piętro" value={listing.floor ? `${listing.floor}/${listing.total_floors || '?'}` : 'Brak danych'} />
            </div>
          </div>

          {/* Photo Analysis Section (Faza 4) */}
          {listing.photo_analysis && (
            <div className="card-premium border-l-4 border-l-indigo-500">
              <h2 className="text-xl font-bold text-white mb-6 flex items-center gap-2">
                <Layers className="w-5 h-5 text-indigo-400" /> Wizualna Ocena Stanu (Moondream AI)
              </h2>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div className="space-y-4">
                  <div className="flex justify-between items-end">
                    <span className="text-sm font-bold text-premium-muted uppercase">Stan wizualny</span>
                    <span className="text-xl font-black text-indigo-400 uppercase">{listing.photo_analysis.condition?.replace('_', ' ')}</span>
                  </div>
                  <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-indigo-500 transition-all duration-1000" 
                      style={{ width: `${(listing.photo_analysis.avg_condition_score || 0) * 10}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-[10px] text-slate-500 font-bold uppercase">
                    <span>Remont</span>
                    <span>Idealny</span>
                  </div>
                </div>

                <div className="bg-slate-800/30 rounded-xl p-4 border border-slate-700/30">
                  <div className="text-xs font-bold text-premium-muted uppercase mb-2">Estymowany koszt remontu</div>
                  <div className="text-2xl font-black text-white">
                    {listing.photo_analysis.estimated_renovation_pct > 0 
                      ? `~${listing.photo_analysis.estimated_renovation_pct}%` 
                      : '0% (Gotowe)'}
                  </div>
                  <div className="text-[10px] text-slate-400 mt-1">Sugerowany narzut na cenę zakupu wg AI</div>
                </div>
              </div>

              <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <div className="text-[10px] font-bold text-emerald-400 uppercase tracking-widest">Wizualne atuty</div>
                  <div className="flex flex-wrap gap-2">
                    {(listing.photo_analysis.positive_features || []).map((f, i) => (
                      <span key={i} className="px-2 py-1 rounded-md bg-emerald-500/5 border border-emerald-500/10 text-[11px] text-emerald-400">
                        {f}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest">Zidentyfikowane wady</div>
                  <div className="flex flex-wrap gap-2">
                    {(listing.photo_analysis.negative_features || []).map((f, i) => (
                      <span key={i} className="px-2 py-1 rounded-md bg-indigo-500/5 border border-indigo-500/10 text-[11px] text-indigo-400">
                        {f}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Pricing & Market Analysis */}
        <div className="space-y-8">
          {/* Price Info Card */}
          <div className="card-premium border-premium-accent/20 bg-gradient-to-br from-premium-card to-slate-900">
            <div className="text-premium-muted text-sm font-bold uppercase tracking-widest mb-1">Cena Ofertowa</div>
            <div className="text-4xl font-black text-white mb-2">{listing.price?.toLocaleString()} PLN</div>
            <div className="text-lg font-medium text-premium-muted">{pricePerM2.toLocaleString()} PLN/m²</div>

            <div className="mt-8 pt-8 border-t border-slate-700/50">
              <div className="flex justify-between items-end mb-3">
                <span className="text-sm font-bold text-premium-muted uppercase">Okazja Score</span>
                <span className="text-2xl font-black text-emerald-400">{Math.round(listing.score * 100)}%</span>
              </div>
              <ScoreBar score={listing.score} className="h-3" />
            </div>
          </div>

          {/* Market Context */}
          <div className="card-premium">
            <h3 className="text-lg font-bold text-white mb-6">Analiza Rynkowa (RCN)</h3>
            <div className="space-y-6">
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-premium-muted">Benchmark RCN ({listing.district})</span>
                  <span className="text-white font-bold">{listing.rcn_benchmark?.toLocaleString() || '---'} zł/m²</span>
                </div>
                <div className="text-xs text-premium-muted">Mediana realnych transakcji w okolicy</div>
              </div>

              {gapPercent !== null && (
                <div className={`p-4 rounded-xl flex items-center justify-between ${gapPercent > 0 ? 'bg-emerald-500/10 border border-emerald-500/20' : 'bg-red-500/10 border border-red-500/20'}`}>
                  <div>
                    <div className="text-xs font-bold uppercase tracking-wider mb-0.5">Potencjał negocjacyjny</div>
                    <div className={`text-lg font-black ${gapPercent > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {gapPercent > 0 ? '-' : '+'}{Math.abs(gapPercent)}% vs RCN
                    </div>
                  </div>
                  {gapPercent > 0 ? <TrendingDown className="w-8 h-8 text-emerald-400/50" /> : <TrendingUp className="w-8 h-8 text-red-400/50" />}
                </div>
              )}

              <div className="pt-4">
                <div className="text-xs text-premium-muted mb-4 uppercase font-bold tracking-widest">Historia ceny</div>
                <div className="h-32 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={listing.price_history}>
                      <Line
                        type="monotone"
                        dataKey="price"
                        stroke="#3b82f6"
                        strokeWidth={3}
                        dot={{ fill: '#3b82f6', r: 4 }}
                      />
                      <Tooltip
                        contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155', color: '#f8fafc' }}
                        itemStyle={{ color: '#f8fafc' }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ParamItem({ icon: Icon, label, value }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2 text-premium-muted">
        <Icon className="w-4 h-4" />
        <span className="text-[10px] font-bold uppercase tracking-wider">{label}</span>
      </div>
      <div className="text-sm font-bold text-white">{value}</div>
    </div>
  );
}
