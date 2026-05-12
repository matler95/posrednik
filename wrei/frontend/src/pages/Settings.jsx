import { useState, useEffect } from 'react';
import { huntApi } from '../api/client';
import { useNavigate } from 'react-router-dom';
import { Settings as SettingsIcon, Save, ArrowLeft, Check, AlertCircle } from 'lucide-react';

const WARSAW_DISTRICTS = [
  "Bemowo", "Białołęka", "Bielany", "Mokotów", "Ochota", "Praga-Południe", 
  "Praga-Północ", "Rembertów", "Śródmieście", "Targówek", "Ursus", 
  "Ursynów", "Wawer", "Wesoła", "Wilanów", "Włochy", "Wola", "Żoliborz"
];

const AVAILABLE_PORTALS = ["otodom", "olx", "morizon", "gratka", "domiporta", "nieruchomosci_online"];

export default function Settings() {
  const navigate = useNavigate();
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const res = await huntApi.getConfig();
        setConfig(res.data);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchConfig();
  }, []);

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      await huntApi.setConfig(config);
      setMessage({ type: 'success', text: 'Konfiguracja zapisana pomyślnie!' });
      setTimeout(() => navigate('/hunt'), 1500);
    } catch (err) {
      setMessage({ type: 'error', text: 'Błąd podczas zapisywania konfiguracji.' });
    } finally {
      setSaving(false);
    }
  };

  const toggleDistrict = (dist) => {
    const districts = config.districts || [];
    if (districts.includes(dist)) {
      setConfig({ ...config, districts: districts.filter(d => d !== dist) });
    } else {
      setConfig({ ...config, districts: [...districts, dist] });
    }
  };

  const togglePortal = (portal) => {
    const portals = config.portals || [];
    if (portals.includes(portal)) {
      setConfig({ ...config, portals: portals.filter(p => p !== portal) });
    } else {
      setConfig({ ...config, portals: [...portals, portal] });
    }
  };

  const toggleRoom = (room) => {
    const rooms = config.rooms || [];
    const rStr = room.toString();
    if (rooms.includes(rStr)) {
      setConfig({ ...config, rooms: rooms.filter(r => r !== rStr) });
    } else {
      setConfig({ ...config, rooms: [...rooms, rStr] });
    }
  };

  if (loading) return <div className="animate-pulse space-y-8"><div className="h-96 card card-accent" /></div>;

  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in duration-500">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="flex items-center gap-2 text-premium-muted hover:text-white transition-colors">
          <ArrowLeft className="w-4 h-4" /> Powrót
        </button>
        <h1 className="text-3xl font-black text-white flex items-center gap-3">
          <SettingsIcon className="text-premium-accent w-8 h-8" />
          Konfiguracja Polowania
        </h1>
      </div>

      {message && (
        <div className={`p-4 rounded-xl flex items-center gap-3 border ${message.type === 'success' ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' : 'bg-red-500/10 border-red-500/20 text-red-400'}`}>
          {message.type === 'success' ? <Check className="w-5 h-5" /> : <AlertCircle className="w-5 h-5" />}
          {message.text}
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-8">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          {/* Basic Params */}
          <div className="card card-accent space-y-6">
            <h2 className="text-lg font-bold text-white border-b border-slate-700/50 pb-4">Parametry Podstawowe</h2>
            
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-bold text-premium-muted uppercase mb-2 block">Cena Min (PLN)</label>
                  <input 
                    type="number" 
                    value={config.min_price} 
                    onChange={e => setConfig({...config, min_price: parseInt(e.target.value)})}
                    className="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-2.5 text-white focus:ring-1 ring-premium-accent outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs font-bold text-premium-muted uppercase mb-2 block">Cena Max (PLN)</label>
                  <input 
                    type="number" 
                    value={config.max_price} 
                    onChange={e => setConfig({...config, max_price: parseInt(e.target.value)})}
                    className="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-2.5 text-white focus:ring-1 ring-premium-accent outline-none"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-bold text-premium-muted uppercase mb-2 block">Metraż Min (m²)</label>
                  <input 
                    type="number" 
                    value={config.min_area} 
                    onChange={e => setConfig({...config, min_area: parseInt(e.target.value)})}
                    className="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-2.5 text-white focus:ring-1 ring-premium-accent outline-none"
                  />
                </div>
                <div>
                  <label className="text-xs font-bold text-premium-muted uppercase mb-2 block">Metraż Max (m²)</label>
                  <input 
                    type="number" 
                    value={config.max_area} 
                    onChange={e => setConfig({...config, max_area: parseInt(e.target.value)})}
                    className="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-2.5 text-white focus:ring-1 ring-premium-accent outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="text-xs font-bold text-premium-muted uppercase mb-2 block">Pokoje</label>
                <div className="flex gap-2">
                  {[1, 2, 3, 4, 5].map(r => (
                    <button
                      key={r}
                      type="button"
                      onClick={() => toggleRoom(r)}
                      className={`w-10 h-10 rounded-lg font-bold border transition-all ${config.rooms?.includes(r.toString()) ? 'bg-premium-accent border-premium-accent text-white' : 'bg-slate-800 border-slate-700 text-premium-muted hover:border-slate-500'}`}
                    >
                      {r}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex items-center gap-3 pt-4">
                <input 
                  type="checkbox" 
                  id="direct_only"
                  checked={config.direct_only} 
                  onChange={e => setConfig({...config, direct_only: e.target.checked})}
                  className="w-5 h-5 rounded border-slate-700 bg-slate-800 text-premium-accent focus:ring-premium-accent"
                />
                <label htmlFor="direct_only" className="text-sm font-bold text-white cursor-pointer">Tylko oferty bezpośrednie</label>
              </div>
            </div>
          </div>

          {/* Portals */}
          <div className="card card-accent space-y-6">
            <h2 className="text-lg font-bold text-white border-b border-slate-700/50 pb-4">Źródła (Portale)</h2>
            <div className="grid grid-cols-2 gap-3">
               {AVAILABLE_PORTALS.map(portal => (
                 <button
                   key={portal}
                   type="button"
                   onClick={() => togglePortal(portal)}
                   className={`px-4 py-2.5 rounded-xl text-xs font-bold border transition-all text-left flex justify-between items-center ${config.portals?.includes(portal) ? 'bg-premium-accent/10 border-premium-accent text-premium-accent' : 'bg-slate-800 border-slate-700 text-premium-muted hover:border-slate-500'}`}
                 >
                   {portal.toUpperCase()}
                   {config.portals?.includes(portal) && <Check className="w-3 h-3" />}
                 </button>
               ))}
            </div>

            <div className="pt-6">
               <label className="text-xs font-bold text-premium-muted uppercase mb-2 block">Minimalny Score dla Alertów</label>
               <input 
                 type="range" 
                 min="0.1" max="0.9" step="0.05"
                 value={config.min_score_alert || 0.25} 
                 onChange={e => setConfig({...config, min_score_alert: parseFloat(e.target.value)})}
                 className="w-full accent-premium-accent h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer"
               />
               <div className="flex justify-between text-[10px] font-black text-premium-muted mt-2">
                 <span>LIBERALNY (10%)</span>
                 <span className="text-premium-accent text-sm">{(config.min_score_alert * 100).toFixed(0)}%</span>
                 <span>RESTRYKCYJNY (90%)</span>
               </div>
            </div>
          </div>
        </div>

        {/* Districts */}
        <div className="card card-accent space-y-6">
          <div className="flex justify-between items-center border-b border-slate-700/50 pb-4">
            <h2 className="text-lg font-bold text-white">Dzielnice (Puste = Całe Miasto)</h2>
            <button 
              type="button" 
              onClick={() => setConfig({...config, districts: []})}
              className="text-xs text-premium-muted hover:text-white"
            >
              Wyczyść wszystkie
            </button>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
             {WARSAW_DISTRICTS.map(dist => (
               <button
                 key={dist}
                 type="button"
                 onClick={() => toggleDistrict(dist)}
                 className={`px-3 py-2 rounded-lg text-[10px] font-bold border transition-all ${config.districts?.includes(dist) ? 'bg-premium-accent border-premium-accent text-white' : 'bg-slate-800 border-slate-700 text-premium-muted hover:border-slate-500'}`}
               >
                 {dist}
               </button>
             ))}
          </div>
        </div>

        <div className="flex justify-end gap-4">
           <button 
             type="button" 
             onClick={() => navigate(-1)}
             className="px-8 py-3 rounded-xl font-bold text-premium-muted hover:text-white transition-colors"
           >
             Anuluj
           </button>
           <button 
             type="submit" 
             disabled={saving}
             className="btn-primary flex items-center gap-2 px-10"
           >
             {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
             Zapisz i Poluj
           </button>
        </div>
      </form>
    </div>
  );
}

function RefreshCw(props) {
  return (
    <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>
  );
}
