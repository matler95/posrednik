import { useState, useEffect } from 'react';
import { marketApi } from '../api/client';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Cell,
  AreaChart, Area
} from 'recharts';
import { BarChart2, TrendingUp, Map, LayoutGrid, Info } from 'lucide-react';

export default function Stats() {
  const [districts, setDistricts] = useState([]);
  const [trend, setTrend] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedDistrict, setSelectedDistrict] = useState(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const [distRes, trendRes] = await Promise.all([
          marketApi.getDistricts(),
          marketApi.getTrend({ district: selectedDistrict })
        ]);
        setDistricts(distRes.data);
        setTrend(trendRes.data.quarterly_trend);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, [selectedDistrict]);

  const handleIngest = async () => {
    setLoading(true);
    try {
      await marketApi.ingest();
      alert('Zadanie importu danych RCN uruchomione. Odśwież za kilka minut.');
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div className="animate-pulse space-y-8"><div className="h-96 card card-accent" /><div className="h-96 card card-accent" /></div>;

  return (
    <div className="space-y-8 animate-in fade-in duration-700">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-black text-white flex items-center gap-3">
            <BarChart2 className="text-premium-accent w-8 h-8" />
            Analityka Rynkowa
          </h1>
          <p className="text-premium-muted mt-1">
            Dane transakcyjne na podstawie bazy RCN (Deweloperuch)
          </p>
        </div>
        <button
          onClick={handleIngest}
          className="text-xs bg-slate-800 hover:bg-slate-700 text-premium-muted px-4 py-2 rounded-xl border border-slate-700 transition-colors"
        >
          Aktualizuj bazę RCN
        </button>
      </div>

      {/* Main Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* District Comparison */}
        <div className="card card-accent h-[500px] flex flex-col">
          <div className="flex justify-between items-center mb-6">
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <LayoutGrid className="w-5 h-5 text-premium-accent" /> Ceny w Dzielnicach
            </h3>
            <span className="text-[10px] bg-slate-800 text-premium-muted px-2 py-1 rounded font-bold">PLN/m²</span>
          </div>
          <div className="flex-grow">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={districts} layout="vertical" margin={{ left: 20 }}>
                <XAxis type="number" hide />
                <YAxis
                  dataKey="district"
                  type="category"
                  tick={{ fill: '#94a3b8', fontSize: 12 }}
                  width={100}
                />
                <Tooltip
                  cursor={{ fill: '#1e293b' }}
                  contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155' }}
                />
                <Bar dataKey="rcn_median" radius={[0, 4, 4, 0]}>
                  {districts.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={index < 3 ? '#3b82f6' : '#1d4ed8'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Historical Trend */}
        <div className="card card-accent h-[500px] flex flex-col">
          <div className="flex justify-between items-center mb-6">
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-emerald-400" /> Trend Historyczny
            </h3>
            <select
              className="bg-slate-800 border-none rounded-lg text-xs text-white px-3 py-1.5 outline-none focus:ring-1 ring-premium-accent"
              onChange={(e) => setSelectedDistrict(e.target.value || null)}
              value={selectedDistrict || ''}
            >
              <option value="">Cała Warszawa</option>
              {districts.map(d => <option key={d.district} value={d.district}>{d.district}</option>)}
            </select>
          </div>
          <div className="flex-grow">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trend}>
                <defs>
                  <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
                <XAxis
                  dataKey="label"
                  tick={{ fill: '#94a3b8', fontSize: 10 }}
                  axisLine={false}
                />
                <YAxis
                  tick={{ fill: '#94a3b8', fontSize: 10 }}
                  axisLine={false}
                  domain={['auto', 'auto']}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155' }}
                />
                <Area
                  type="monotone"
                  dataKey="median_sqm"
                  stroke="#3b82f6"
                  strokeWidth={4}
                  fillOpacity={1}
                  fill="url(#colorPrice)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* District Heatmap Table */}
      <div className="card card-accent overflow-hidden">
        <div className="p-6 border-b border-slate-700/50 flex justify-between items-center">
          <h3 className="text-lg font-bold text-white flex items-center gap-2">
            <Map className="w-5 h-5 text-premium-accent" /> Zestawienie Dzielnicowe
          </h3>
          <div className="flex items-center gap-2 text-xs text-premium-muted">
            <Info className="w-3 h-3" /> Kliknij w dzielnicę, aby zobaczyć trend
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-800/50">
                <th className="px-6 py-4 text-xs font-bold text-premium-muted uppercase tracking-widest">Dzielnica</th>
                <th className="px-6 py-4 text-xs font-bold text-premium-muted uppercase tracking-widest text-right">Mediana (m²)</th>
                <th className="px-6 py-4 text-xs font-bold text-premium-muted uppercase tracking-widest text-right">Średnia (m²)</th>
                <th className="px-6 py-4 text-xs font-bold text-premium-muted uppercase tracking-widest text-right">Próba</th>
                <th className="px-6 py-4 text-xs font-bold text-premium-muted uppercase tracking-widest text-center">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/50">
              {districts.map((d) => {
                const maxMedian = Math.max(...districts.map(x => x.rcn_median || 0));
                const intensity = d.rcn_median ? (d.rcn_median / maxMedian) : 0;
                // Heatmap color from slate-900 to blue-900
                const bgColor = `rgba(59, 130, 246, ${intensity * 0.15})`;
                
                return (
                  <tr
                    key={d.district}
                    className="hover:bg-slate-800/50 transition-colors cursor-pointer group"
                    onClick={() => setSelectedDistrict(d.district)}
                    style={{ backgroundColor: bgColor }}
                  >
                    <td className="px-6 py-4 font-bold text-white group-hover:text-premium-accent transition-colors">
                      {d.district}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <span className="text-white font-mono font-bold">
                        {Math.round(d.rcn_median).toLocaleString()}
                      </span>
                      <span className="text-[10px] text-premium-muted ml-1">zł</span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <span className="text-slate-300 font-mono">
                        {Math.round(d.offer_avg).toLocaleString()}
                      </span>
                      <span className="text-[10px] text-premium-muted ml-1">zł</span>
                    </td>
                    <td className="px-6 py-4 text-right text-premium-muted font-mono">
                      {d.count}
                    </td>
                    <td className="px-6 py-4 text-center">
                      <div className="flex justify-center items-center gap-1.5">
                        <span className={cn(
                          "w-2 h-2 rounded-full",
                          d.count > 50 ? "bg-emerald-500 shadow-[0_0_8px_#10b981]" : 
                          d.count > 10 ? "bg-amber-500" : "bg-red-500"
                        )} />
                        <span className="text-[10px] text-premium-muted uppercase font-bold">
                          {d.count > 50 ? "Stable" : d.count > 10 ? "Partial" : "Weak"}
                        </span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function cn(...inputs) {
  return inputs.filter(Boolean).join(' ');
}
