import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import SwarnaLogo from '../../components/brand/SwarnaLogo';
import SwarnaHeroArt from '../../components/brand/SwarnaHeroArt';
import { useTheme } from '../../hooks/useTheme';
import clientApi from '../../api/client';
import './Login.css';

const FEATURES = [
  {
    icon: 'public',
    tone: 'mint',
    title: 'Campaigns that dial',
    body: 'Start a list. Swarna places the calls and stays on script.',
  },
  {
    icon: 'verified_user',
    tone: 'peach',
    title: 'Secure by default',
    body: 'Organization keys, isolated workspaces, nothing shared by accident.',
  },
  {
    icon: 'graphic_eq',
    tone: 'sky',
    title: 'Gemini answers live',
    body: 'The agent greets from your opening line, then answers from knowledge.',
  },
];

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
    if (responseData.client_id) {
      localStorage.setItem('client_id', responseData.client_id);
    }
    setIsRedirecting(true);
    setTimeout(() => navigate('/app'), 200);
  }, [navigate]);

  const handleAuthenticate = useCallback(async () => {
    const key = apiKey.trim();
    if (!key) {
      setIsShaking(true);
      setTimeout(() => setIsShaking(false), 400);
      document.getElementById('sign-in')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
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

  const scrollToSignIn = () => {
    document.getElementById('sign-in')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  return (
    <div className={`cl-login ${theme === 'dark' ? 'dark' : ''} ${isRedirecting ? 'redirect-active' : ''}`}>
      <div className="redirect-overlay" />

      <header className="cl-login__header">
        <SwarnaLogo variant="dark" size="md" />
        <nav className="cl-login__nav" aria-label="Page">
          <a href="#features">Features</a>
          <a href="#how">How it works</a>
          <a href="#sign-in">Access</a>
        </nav>
        <div className="cl-login__header-actions">
          <button type="button" className="cl-login__icon-btn" onClick={toggleTheme} aria-label="Toggle theme">
            <span className="material-symbols-outlined">
              {theme === 'dark' ? 'light_mode' : 'dark_mode'}
            </span>
          </button>
          <button type="button" className="cl-login__cta" onClick={scrollToSignIn}>
            Sign in
          </button>
        </div>
      </header>

      <section className="cl-login__hero">
        <div className="cl-login__hero-copy">
          <span className="cl-login__eyebrow">
            <span className="material-symbols-outlined">graphic_eq</span>
            Voice receptionist
          </span>
          <h1>You can call anyone, anytime — on script</h1>
          <p>
            Swarna places the call, greets in your words, and answers with Gemini.
            Campaigns, leads, and transcripts stay easy to follow.
          </p>
          <div className="cl-login__hero-actions">
            <button type="button" className="cl-login__cta cl-login__cta--lg" onClick={scrollToSignIn}>
              Open workspace
              <span className="material-symbols-outlined">arrow_forward</span>
            </button>
            <a className="cl-login__ghost" href="#how">See how it works</a>
          </div>
        </div>
        <SwarnaHeroArt />
      </section>

      <section className="cl-login__trust" aria-label="What you get">
        <span>Live calls</span>
        <span>Script follow-through</span>
        <span>Gemini answers</span>
        <span>Private workspaces</span>
        <span>Clear transcripts</span>
      </section>

      <section className="cl-login__features" id="features">
        <p className="cl-login__kicker">Our features</p>
        <h2>Everything you need to run voice outreach</h2>
        <div className="cl-login__feature-grid">
          {FEATURES.map((item) => (
            <article key={item.title} className="cl-login__feature">
              <div className={`cl-login__feature-icon cl-login__feature-icon--${item.tone}`}>
                <span className="material-symbols-outlined">{item.icon}</span>
              </div>
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="cl-login__how" id="how">
        <div>
          <p className="cl-login__kicker">How it works</p>
          <h2>Three steps. Then the phone rings.</h2>
        </div>
        <ol className="cl-login__steps">
          <li><strong>1.</strong> Create a campaign and paste your script.</li>
          <li><strong>2.</strong> Upload leads. Swarna dials with your voice agent.</li>
          <li><strong>3.</strong> Watch answers, interest, and transcripts in one view.</li>
        </ol>
      </section>

      <section className="cl-login__auth" id="sign-in">
        <div className={`cl-login__card ${isShaking ? 'cl-login__card--shake' : ''}`}>
          <div className="cl-login__icon" aria-hidden>
            <span className="material-symbols-outlined">vpn_key</span>
          </div>
          <h2>Client access</h2>
          <p className="cl-login__subtitle">Enter your organization key. Nothing else to remember.</p>

          <div className="cl-login__field">
            <label className="cl-login__label" htmlFor="api-key-input">API key</label>
            <div className="cl-login__input-wrap">
              <input
                id="api-key-input"
                className={`cl-login__input ${isError ? 'cl-login__input--error' : ''} ${isSuccess ? 'cl-login__input--success' : ''}`}
                type="password"
                placeholder="Paste your client key"
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
            className="cl-login__cta cl-login__cta--block"
            onClick={handleAuthenticate}
            disabled={isSuccess || loading}
          >
            {loading && <span className="cl-login__spinner" aria-hidden />}
            {isSuccess ? 'Welcome in' : loading ? 'Checking key…' : 'Enter workspace'}
            {!loading && !isSuccess && (
              <span className="material-symbols-outlined">arrow_forward</span>
            )}
          </button>
        </div>
      </section>

      <footer className="cl-login__footer">
        <span>© 2026 Swarna</span>
        <span>Private · Encrypted in transit · Easy to leave</span>
      </footer>
    </div>
  );
};

export default Login;
