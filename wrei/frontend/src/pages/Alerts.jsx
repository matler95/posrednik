import { useState, useEffect } from 'react';
import { Bell, ShieldCheck, TrendingDown, Zap, MapPin, ExternalLink, Clock } from 'lucide-react';
import { alertsApi } from '../api/client';

export default function Alerts() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchAlerts = async () => {
      try {
        const res = await alertsApi.get();
        setAlerts(res.data);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchAlerts();
  }, []);

  return (
    <div className="space-y-8 animate-in fade-in duration-700">
      <div className="flex justify-between items-start">
         <div>
            <h1 className="text-3xl font-black text-white flex items-center gap-3">
              <Bell className="text-premium-accent w-8 h-8" />
              Centrum Alertów
            </h1>
            <p className="text-premium-muted mt-1">
              Historia automatycznych powiadomień o okazjach
            </p>
         </div>
         <div className="bg-slate-800/50 px-4 py-2 rounded-xl border border-slate-700 flex items-center gap-3">
            <ShieldCheck className="w-5 h-5 text-emerald-400" />
            <div>
               <div className="text-[10px] font-bold text-premium-muted uppercase">Strażnik</div>
               <div className="text-xs text-white font-bold">Aktywny (Telegram)</div>
            </div>
         </div>
      </div>

      <div className="grid grid-cols-1 gap-4">
        {loading ? (
          <div className="animate-pulse space-y-4">
            {[1, 2, 3].map(i => <div key={i} className="h-32 card-premium" />)}
          </div>
        ) : alerts.length === 0 ? (
          <div className="card-premium py-20 text-center">
            <p className="text-premium-muted">Brak aktywnych alertów w historii.</p>
          </div>
        ) : (
          alerts.map((alert) => (
            <div key={alert.id} className="card-premium flex gap-6 hover:border-premium-accent/40 transition-all group">
              <div className="w-24 h-24 rounded-xl overflow-hidden shrink-0 bg-slate-800">
                <img src={alert.images?.[0] || 'https://via.placeholder.com/150'} className="w-full h-full object-cover" />
              </div>
              <div className="flex-grow">
                <div className="flex justify-between items-start">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`text-[10px] font-black uppercase px-2 py-0.5 rounded ${
                        alert.alert_type === 'price_drop' ? 'bg-emerald-500/10 text-emerald-400' :
                        alert.alert_type === 'new_high_score' ? 'bg-blue-500/10 text-blue-400' :
                        'bg-amber-500/10 text-amber-400'
                      }`}>
                        {alert.alert_type === 'price_drop' ? 'Spadek Ceny' : 
                         alert.alert_type === 'new_high_score' ? 'Nowa Okazja' : 'Anomalia'}
                      </span>
                      <span className="text-[10px] text-premium-muted flex items-center gap-1">
                        <Clock className="w-3 h-3" /> {new Date(alert.triggered_at).toLocaleString()}
                      </span>
                    </div>
                    <h3 className="text-white font-bold text-lg group-hover:text-premium-accent transition-colors">{alert.title}</h3>
                    <div className="flex items-center gap-4 mt-2 text-sm text-premium-muted">
                      <span className="flex items-center gap-1"><MapPin className="w-3 h-3" /> {alert.district}</span>
                      <span className="font-bold text-white">{alert.price?.toLocaleString()} PLN</span>
                      <span>{alert.area} m²</span>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-black text-emerald-400">{Math.round(alert.score * 100)}%</div>
                    <div className="text-[10px] text-premium-muted uppercase font-bold">Opportunity Score</div>
                  </div>
                </div>
                
                <div className="mt-4 flex items-center justify-between">
                   <div className="flex items-center gap-6">
                      {alert.alert_type === 'price_drop' && (
                        <div className="flex items-center gap-2">
                           <TrendingDown className="w-4 h-4 text-emerald-400" />
                           <span className="text-sm text-emerald-400 font-bold">
                             {alert.old_value?.toLocaleString()} → {alert.new_value?.toLocaleString()} PLN
                           </span>
                        </div>
                      )}
                      {alert.alert_type === 'new_high_score' && (
                        <div className="flex items-center gap-2">
                           <Zap className="w-4 h-4 text-blue-400" />
                           <span className="text-sm text-blue-400 font-bold">Wysoki potencjał inwestycyjny</span>
                        </div>
                      )}
                   </div>
                   <a href={alert.url} target="_blank" rel="noreferrer" className="text-premium-accent flex items-center gap-1 text-sm font-bold hover:underline">
                      Zobacz ogłoszenie <ExternalLink className="w-4 h-4" />
                   </a>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
