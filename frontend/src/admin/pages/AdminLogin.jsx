import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTheme } from '../hooks/useTheme';
import { useAdminAuth } from '../contexts/AdminAuthContext';
import adminApi from '../../shared/api/admin';
import SwarnaLogo from '../../components/brand/SwarnaLogo';
import SwarnaHeroArt from '../../components/brand/SwarnaHeroArt';
import '../../pages/client/Login.css';

export default function AdminLogin() {
  const { theme, toggleTheme } = useTheme();
  const { login, logout } = useAdminAuth();
  const navigate = useNavigate();
  const [status, setStatus] = useState('idle');
  const [secretKey, setSecretKey] = useState('');
  const secretInputRef = useRef(null);
  const cardRef = useRef(null);

  useEffect(() => {
    secretInputRef.current?.focus();
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if ((status !== 'idle' && status !== 'error') || !secretKey) return;
    setStatus('authenticating');
    try {
      login(secretKey);
      await adminApi.get('/internal/health');
      navigate('/admin');
    } catch {
      logout();
      setStatus('error');
      if (cardRef.current) {
        cardRef.current.classList.remove('cl-login__card--shake');
        void cardRef.current.offsetWidth;
        cardRef.current.classList.add('cl-login__card--shake');
      }
    }
  };

  const handleRetry = (e) => {
    if (e) e.preventDefault();
    setStatus('idle');
    secretInputRef.current?.focus();
    secretInputRef.current?.select();
  };

  return (
    <div className={`cl-login ${theme === 'dark' ? 'dark' : ''}`}>
      <header className="cl-login__header">
        <SwarnaLogo variant="dark" size="md" />
        <nav className="cl-login__nav" aria-label="Page">
          <a href="#sign-in">Access</a>
        </nav>
        <div className="cl-login__header-actions">
          <button type="button" className="cl-login__icon-btn" onClick={toggleTheme} aria-label="Toggle theme">
            <span className="material-symbols-outlined">
              {theme === 'dark' ? 'light_mode' : 'dark_mode'}
            </span>
          </button>
          <a className="cl-login__cta" href="#sign-in">Admin sign in</a>
        </div>
      </header>

      <section className="cl-login__hero">
        <div className="cl-login__hero-copy">
          <span className="cl-login__eyebrow">
            <span className="material-symbols-outlined">admin_panel_settings</span>
            Control console
          </span>
          <h1>Run the whole voice operation from one calm screen</h1>
          <p>Clients, campaigns, scripts, and live calls — without the clutter.</p>
        </div>
        <SwarnaHeroArt />
      </section>

      <section className="cl-login__auth" id="sign-in">
        <form ref={cardRef} className="cl-login__card" onSubmit={handleSubmit}>
          <div className="cl-login__icon" aria-hidden>
            <span className="material-symbols-outlined">key</span>
          </div>
          <h2>Swarna Admin</h2>
          <p className="cl-login__subtitle">
            {status === 'error' ? 'That key did not match. Try again.' : 'Enter the operator key to continue.'}
          </p>
          <label className="cl-login__label" htmlFor="secretKey">Admin key</label>
          <div className="cl-login__input-wrap">
            <input
              ref={secretInputRef}
              id="secretKey"
              type="password"
              className={`cl-login__input ${status === 'error' ? 'cl-login__input--error' : ''}`}
              value={secretKey}
              onChange={(e) => {
                setSecretKey(e.target.value);
                if (status === 'error') setStatus('idle');
              }}
              placeholder="Admin secret key"
              autoComplete="off"
              disabled={status === 'authenticating'}
            />
          </div>
          <p className="cl-login__error">{status === 'error' ? 'Invalid secret key.' : ''}</p>
          {status === 'error' ? (
            <button type="button" className="cl-login__cta cl-login__cta--block" onClick={handleRetry}>
              Retry
            </button>
          ) : (
            <button type="submit" className="cl-login__cta cl-login__cta--block" disabled={status === 'authenticating'}>
              {status === 'authenticating' ? 'Checking…' : 'Enter console'}
              {status !== 'authenticating' && <span className="material-symbols-outlined">arrow_forward</span>}
            </button>
          )}
        </form>
      </section>
    </div>
  );
}
