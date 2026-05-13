import React from 'react';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("[ErrorBoundary] Caught error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ 
          padding: '2rem', 
          textAlign: 'center', 
          background: '#0f172a', 
          color: '#f1f5f9', 
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center',
          fontFamily: 'system-ui, sans-serif'
        }}>
          <h1 style={{ fontSize: '2rem', marginBottom: '1rem' }}>Ups! Coś poszło nie tak.</h1>
          <p style={{ color: '#94a3b8', marginBottom: '2rem' }}>Wystąpił nieoczekiwany błąd w aplikacji frontendowej.</p>
          <pre style={{ 
            background: '#1e293b', 
            padding: '1rem', 
            borderRadius: '8px', 
            maxWidth: '80%', 
            overflow: 'auto',
            textAlign: 'left',
            fontSize: '0.875rem',
            color: '#ef4444',
            border: '1px solid #334155'
          }}>
            {this.state.error?.toString()}
          </pre>
          <button 
            onClick={() => window.location.reload()}
            style={{ 
              marginTop: '2rem', 
              padding: '0.75rem 1.5rem', 
              background: '#3b82f6', 
              border: 'none', 
              borderRadius: '6px', 
              color: '#fff', 
              fontWeight: '600',
              cursor: 'pointer',
              transition: 'background 0.2s'
            }}
            onMouseOver={(e) => e.target.style.background = '#2563eb'}
            onMouseOut={(e) => e.target.style.background = '#3b82f6'}
          >
            Odśwież stronę
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
