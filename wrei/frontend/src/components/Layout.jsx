import { Outlet, Link, useLocation } from 'react-router-dom';
import { Target, BarChart2, Bell, Settings, Home } from 'lucide-react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs) {
  return twMerge(clsx(inputs));
}

export function Layout() {
  const location = useLocation();

  const navItems = [
    { name: 'Polowanie', path: '/hunt', icon: Target },
    { name: 'Statystyki', path: '/stats', icon: BarChart2 },
    { name: 'Alerty', path: '/alerts', icon: Bell },
  ];

  return (
    <div className="min-h-screen flex flex-col">
      <header className="glass-header">
        <div className="container mx-auto px-4 flex justify-between items-center">
          <Link to="/" className="flex items-center gap-2 group">
            <div className="bg-premium-accent p-2 rounded-lg group-hover:rotate-12 transition-transform">
              <Home className="text-white w-6 h-6" />
            </div>
            <span className="text-2xl font-bold tracking-tight text-white">WREI</span>
          </Link>
          
          <nav className="hidden md:flex items-center gap-8">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = location.pathname.startsWith(item.path);
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={cn(
                    "flex items-center gap-2 text-sm font-medium transition-colors",
                    isActive ? "text-premium-accent" : "text-premium-muted hover:text-white"
                  )}
                >
                  <Icon className="w-4 h-4" />
                  {item.name}
                </Link>
              );
            })}
          </nav>

          <div className="flex items-center gap-4">
             <button className="p-2 text-premium-muted hover:text-white transition-colors">
               <Settings className="w-5 h-5" />
             </button>
             <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-premium-accent to-blue-400 border border-slate-700"></div>
          </div>
        </div>
      </header>

      <main className="flex-grow container mx-auto px-4 py-8">
        <Outlet />
      </main>

      <footer className="border-t border-slate-700/50 py-8 text-center text-premium-muted text-sm">
        WREI &copy; 2026 • Sniper Mode Active
      </footer>
    </div>
  );
}
