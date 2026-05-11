import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { Target, BarChart2, Bell, Settings, Zap } from 'lucide-react';

export function Layout() {
  return (
    <div style={{ display: 'flex', minHeight: '100vh', position: 'relative', zIndex: 1 }}>
      {/* Sidebar */}
      <aside style={{
        width: 220,
        background: 'var(--bg2)',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        padding: '24px 12px',
        flexShrink: 0,
        position: 'fixed',
        top: 0,
        bottom: 0,
        left: 0,
        zIndex: 10,
      }}>
        {/* Logo */}
        <div style={{ padding: '0 8px 24px', borderBottom: '1px solid var(--border)', marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              background: 'var(--accent)',
              width: 32,
              height: 32,
              borderRadius: 8,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              <Zap size={18} color="white" />
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 16, letterSpacing: '-0.02em' }}>WREI</div>
              <div style={{ fontSize: 10, color: 'var(--muted)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>Hunter v2</div>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 4 }}>
          <NavLink to="/hunt" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <Target size={16} />
            Polowanie
          </NavLink>
          <NavLink to="/stats" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <BarChart2 size={16} />
            Statystyki
          </NavLink>
          <NavLink to="/alerts" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <Bell size={16} />
            Alerty
          </NavLink>
        </nav>

        {/* Settings link at bottom */}
        <NavLink to="/hunt/settings" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
          <Settings size={16} />
          Konfiguracja
        </NavLink>
      </aside>

      {/* Main content */}
      <main style={{ marginLeft: 220, flex: 1, padding: '32px 40px', maxWidth: 'calc(100vw - 220px)' }}>
        <Outlet />
      </main>
    </div>
  );
}