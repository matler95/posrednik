import { Outlet, NavLink } from 'react-router-dom';
import { Target, BarChart2, Bell, Settings, Zap, Menu, X } from 'lucide-react';
import { useState, useEffect } from 'react';

export function Layout() {
  const [isMobile, setIsMobile] = useState(window.innerWidth < 1024);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < 1024;
      setIsMobile(mobile);
      if (!mobile) setMenuOpen(false);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const navItems = [
    { to: "/hunt", icon: Target, label: "Polowanie" },
    { to: "/stats", icon: BarChart2, label: "Statystyki" },
    { to: "/alerts", icon: Bell, label: "Alerty" },
  ];

  const sidebarWidth = 220;

  return (
    <div style={{ display: 'flex', flexDirection: isMobile ? 'column' : 'row', minHeight: '100vh', position: 'relative', zIndex: 1 }}>
      {/* Mobile Header */}
      {isMobile && (
        <header style={{
          height: 60,
          background: 'var(--bg2)',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 16px',
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          zIndex: 100,
          backdropFilter: 'blur(10px)',
        }}>
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
            <div style={{ fontWeight: 700, fontSize: 18 }}>WREI</div>
          </div>
          <button 
            onClick={() => setMenuOpen(!menuOpen)} 
            style={{ 
              background: 'rgba(255,255,255,0.05)', 
              border: '1px solid var(--border)', 
              color: 'var(--text)',
              padding: 8,
              borderRadius: 8,
              cursor: 'pointer'
            }}
          >
            {menuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </header>
      )}

      {/* Sidebar / Mobile Nav Overlay */}
      <aside style={{
        width: isMobile ? '100%' : sidebarWidth,
        background: 'var(--bg2)',
        borderRight: isMobile ? 'none' : '1px solid var(--border)',
        display: (isMobile && !menuOpen) ? 'none' : 'flex',
        flexDirection: 'column',
        padding: '24px 12px',
        flexShrink: 0,
        position: 'fixed',
        top: isMobile ? 60 : 0,
        bottom: 0,
        left: 0,
        zIndex: 90,
        transition: 'transform 0.3s ease',
        overflowY: 'auto'
      }}>
        {!isMobile && (
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
        )}

        <nav style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 4 }}>
          {navItems.map(item => (
            <NavLink 
              key={item.to} 
              to={item.to} 
              className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
              onClick={() => setMenuOpen(false)}
            >
              <item.icon size={16} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <NavLink 
          to="/hunt/settings" 
          className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
          onClick={() => setMenuOpen(false)}
          style={{ marginTop: 16, borderTop: isMobile ? '1px solid var(--border)' : 'none', paddingTop: isMobile ? 16 : 0 }}
        >
          <Settings size={16} />
          Konfiguracja
        </NavLink>
      </aside>

      {/* Main content */}
      <main style={{ 
        marginLeft: isMobile ? 0 : sidebarWidth, 
        marginTop: isMobile ? 60 : 0,
        flex: 1, 
        padding: isMobile ? '16px' : '32px 40px', 
        maxWidth: isMobile ? '100vw' : `calc(100vw - ${sidebarWidth}px)`,
        minWidth: 0
      }}>
        <Outlet />
      </main>
    </div>
  );
}