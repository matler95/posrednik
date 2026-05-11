import { Bell, ShieldCheck } from 'lucide-react';

export default function Alerts() {
  return (
    <div className="space-y-8 animate-in fade-in duration-700">
      <div>
         <h1 className="text-3xl font-black text-white flex items-center gap-3">
           <Bell className="text-premium-accent w-8 h-8" />
           Zarządzanie Alertami
         </h1>
         <p className="text-premium-muted mt-1">
           Powiadomienia o nowych okazjach spełniających kryteria polowania
         </p>
      </div>

      <div className="card-premium py-20 text-center flex flex-col items-center">
         <div className="bg-premium-accent/10 p-6 rounded-full mb-6">
            <ShieldCheck className="w-12 h-12 text-premium-accent" />
         </div>
         <h2 className="text-2xl font-bold text-white mb-2">Automatyczny Strażnik</h2>
         <p className="text-premium-muted max-w-md mx-auto">
           System skanuje portale 24/7. Jeśli znajdziemy ofertę ze score powyżej progu Twojego polowania, otrzymasz powiadomienie na Telegram.
         </p>
         
         <div className="mt-10 grid grid-cols-1 md:grid-cols-2 gap-6 w-full max-w-2xl">
            <div className="bg-slate-800/50 p-6 rounded-2xl border border-slate-700 text-left">
               <div className="text-xs font-bold text-premium-accent uppercase mb-2">Kanał: Telegram</div>
               <div className="text-white font-bold text-lg mb-4">Status: Aktywny ✅</div>
               <button className="text-xs bg-slate-700 hover:bg-slate-600 px-3 py-1.5 rounded-lg transition-colors">Testuj połączenie</button>
            </div>
            <div className="bg-slate-800/50 p-6 rounded-2xl border border-slate-700 text-left">
               <div className="text-xs font-bold text-premium-muted uppercase mb-2">Próg Alertu</div>
               <div className="text-white font-bold text-lg mb-4">Okazja Score &gt; 25%</div>
               <button className="text-xs bg-slate-700 hover:bg-slate-600 px-3 py-1.5 rounded-lg transition-colors">Zmień próg</button>
            </div>
         </div>
      </div>
    </div>
  );
}
