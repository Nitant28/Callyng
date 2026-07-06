import { Component } from 'react';

export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 24,
          fontFamily: 'Inter, sans-serif',
          background: '#f6f8fc',
        }}
        >
          <div style={{
            maxWidth: 480,
            background: '#fff',
            borderRadius: 18,
            padding: 32,
            boxShadow: '0 12px 40px rgba(15,23,42,.08)',
          }}
          >
            <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 8 }}>Something went wrong</h1>
            <p style={{ color: '#64748b', marginBottom: 16, fontSize: 14 }}>
              The app hit an error while loading. Try refreshing the page.
            </p>
            <pre style={{
              fontSize: 12,
              background: '#f1f5f9',
              padding: 12,
              borderRadius: 8,
              overflow: 'auto',
              color: '#b91c1c',
            }}
            >
              {this.state.error.message}
            </pre>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
