import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import CanvasBackground from '../../components/shared/CanvasBackground';
import BhuvisXLogo from '../../components/brand/BhuvisXLogo';
import { useTheme } from '../../hooks/useTheme';
import clientApi from '../../api/client';
import './Login.css';

const Login = () => {
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();
  const [apiKey, setApiKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const [isError, setIsError] = useState(false);
  const [errorMessage, setErrorMessage] = useState('Invalid client key');
  const [isShaking, setIsShaking] = useState(false);
  const [isRedirecting, setIsRedirecting] = useState(false);

  const triggerError = useCallback((message = 'Invalid client key') => {
    setIsError(true);
    setErrorMessage(message);
    setIsSuccess(false);
    setIsShaking(true);
    setTimeout(() => setIsShaking(false), 400);
  }, []);

  const triggerSuccess = useCallback((validKey, responseData = {}) => {
    setIsSuccess(true);
    setIsError(false);
    setErrorMessage('');
    localStorage.setItem('client_api_key', validKey);
    if (responseData.client_name) {
      localStorage.setItem('client_name', responseData.client_name);
    }
    setIsRedirecting(true);
    setTimeout(() => navigate('/app'), 200);
  }, [navigate]);

  const handleAuthenticate = useCallback(async () => {
    const key = apiKey.trim();
    if (!key) {
      setIsShaking(true);
      setTimeout(() => setIsShaking(false), 400);
      return;
    }

    setLoading(true);
    setIsError(false);

    try {
      const response = await clientApi.get('/api/credits', {
        headers: { Authorization: `Bearer ${key}` },
      });
      if (response.status === 200) {
        triggerSuccess(key, response.data || {});
      } else {
        triggerError(response.data?.detail || 'Invalid client key');
      }
    } catch (err) {
      triggerError(err.customErrorMessage || err.response?.data?.detail || 'Invalid client key');
    } finally {
      setLoading(false);
    }
  }, [apiKey, triggerError, triggerSuccess]);

  return (
    <div className={`cl-login ${theme === 'dark' ? 'dark' : ''} ${isRedirecting ? 'redirect-active' : ''}`}>
      <CanvasBackground />
      <div className="redirect-overlay" />

      <header className="cl-login__header">
        <div className="cl-login__brand">
          <BhuvisXLogo variant="dark" size="lg" />
        </div>
        <button type="button" className="cl-login__theme-btn" onClick={toggleTheme} aria-label="Toggle theme">
          <span className="material-symbols-outlined">
            {theme === 'dark' ? 'light_mode' : 'dark_mode'}
          </span>
        </button>
      </header>

      <main className="cl-login__main">
        <div className="cl-login__card">
          <div className="cl-login__icon" aria-hidden>
            <span className="material-symbols-outlined">vpn_key</span>
          </div>
          <h1 className="cl-login__title">Client Access</h1>
          <p className="cl-login__subtitle">
            Enter your organization&apos;s API key to sign in securely.
          </p>

          <div className="cl-login__field">
            <label className="cl-login__label" htmlFor="api-key-input">API Key</label>
            <div className="cl-login__input-wrap">
              <input
                id="api-key-input"
                className={`cl-login__input ${isError ? 'cl-login__input--error' : ''} ${isSuccess ? 'cl-login__input--success' : ''}`}
                type="password"
                placeholder="Enter client API key"
                value={apiKey}
                onChange={(e) => {
                  setApiKey(e.target.value);
                  if (isError) setIsError(false);
                }}
                disabled={isSuccess || loading}
                onKeyDown={(e) => e.key === 'Enter' && handleAuthenticate()}
                autoComplete="off"
              />
              <span className={`cl-login__check material-symbols-outlined ${isSuccess ? 'cl-login__check--visible' : ''}`}>
                check_circle
              </span>
            </div>
            <p className="cl-login__error">{isError ? errorMessage : ''}</p>
          </div>

          <button
            type="button"
            className={`cl-login__btn ${isShaking ? 'cl-login__btn--shake' : ''}`}
            onClick={handleAuthenticate}
            disabled={isSuccess || loading}
          >
            {loading && <span className="cl-login__spinner" aria-hidden />}
            {isSuccess ? 'Success' : loading ? 'Validating…' : 'Authenticate'}
            {!loading && !isSuccess && (
              <span className="material-symbols-outlined" style={{ fontSize: 18 }}>arrow_forward</span>
            )}
          </button>
        </div>
      </main>

      <footer className="cl-login__footer">
        <span>© 2026 AakashVani · Enterprise-grade security</span>
      </footer>
    </div>
  );
};

export default Login;
