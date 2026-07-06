import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import CanvasBackground from '../components/CanvasBackground';
import { useTheme } from '../hooks/useTheme';
import clientApi from '../../api/client';

import { ThemeToggle } from '../components/ui';
import { Button } from '../components/ui';

const Login = () => {
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();
  const [apiKey, setApiKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const [isError, setIsError] = useState(false);
  const [isShaking, setIsShaking] = useState(false);
  const [isRedirecting, setIsRedirecting] = useState(false);
  
  const submitBtnRef = useRef(null);

  const triggerError = useCallback(() => {
    setIsError(true);
    setIsShaking(true);
    setTimeout(() => {
      setIsShaking(false);
    }, 500);
  }, []);

  const triggerSuccess = useCallback((validKey) => {
    setIsSuccess(true);
    localStorage.setItem('client_api_key', validKey);
    
    // Trigger redirect transition immediately for an enterprise feel
    setIsRedirecting(true);
    setTimeout(() => {
      navigate('/app');
    }, 150);
  }, [navigate]);

  const handleAuthenticate = useCallback(async (keyToVerify) => {
    const key = keyToVerify !== undefined ? keyToVerify : apiKey;
    if (!key.trim()) {
      setIsShaking(true);
      setTimeout(() => setIsShaking(false), 500);
      return;
    }

    setLoading(true);
    setIsError(false);

    try {
      // Real API validation call
      const response = await clientApi.get('/api/credits', {
        headers: {
          Authorization: `Bearer ${key}`,
        },
      });

      if (response.status === 200) {
        triggerSuccess(key);
      } else {
        triggerError();
      }
    } catch (err) {
      console.error('Auth verification failed:', err);
      triggerError();
    } finally {
      setLoading(false);
    }
  }, [apiKey, triggerError, triggerSuccess]);

  useEffect(() => {
    if (isError) {
      setIsError(false);
    }
  }, [apiKey]);

  return (
    <div className={isRedirecting ? 'redirect-active' : ''}>
      <CanvasBackground />
      <div className="redirect-overlay"></div>

      {/* Top Navigation */}
      <header className="fixed top-0 w-full flex justify-between items-center px-margin-desktop py-stack-md z-50">
        <div className="font-headline-md text-headline-md font-extrabold text-primary dark:text-molten-primary tracking-tight animate-stagger-1">
          Dev Client
        </div>
        <ThemeToggle className="animate-stagger-1" />
      </header>

      {/* Main Content */}
      <main className="relative h-screen flex flex-col items-center justify-center px-margin-mobile z-10">
        <div className="w-full max-w-[480px] text-center space-y-stack-lg">
          {/* Branding/Header */}
          <div className="space-y-stack-sm animate-stagger-2">
            <h1 className="font-headline-xl text-headline-xl text-primary dark:text-molten-primary tracking-tighter">
              Client Access
            </h1>
            <p className="font-body-md text-body-md text-on-surface-variant dark:text-molten-text-muted">
              Enter your organization’s encrypted API key to proceed.
            </p>
          </div>

          {/* Input Section */}
          <div
            className={`relative transition-all duration-500 animate-stagger-3 ${isSuccess ? 'checkmark-active' : ''}`}
            id="login-container"
          >
            <div className="relative flex flex-col items-start">
              <div className="relative flex items-center w-full">
                <input
                  className={`w-full py-5 px-6 rounded-lg bg-arctic-surface dark:bg-molten-surface border-2 border-outline-variant dark:border-outline text-body-lg font-body-lg focus:outline-none focus:ring-2 focus:ring-primary dark:focus:ring-molten-primary transition-all-custom placeholder:text-outline/50 tabular-nums disabled:opacity-70 disabled:cursor-not-allowed ${
                    isSuccess ? 'api-success-border' : ''
                  } ${isError ? 'border-error dark:border-molten-error input-error-pulse' : ''}`}
                  id="api-key-input"
                  placeholder="Enter Client API Key"
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  disabled={isSuccess || loading}
                  onKeyDown={(e) => e.key === 'Enter' && handleAuthenticate()}
                />
                <div
                  className={`absolute right-6 transition-opacity duration-300 pointer-events-none flex items-center ${
                    isSuccess ? 'opacity-100' : 'opacity-0'
                  }`}
                  id="success-indicator"
                >
                  <svg
                    className="checkmark text-secondary dark:text-molten-success"
                    viewBox="0 0 52 52"
                    xmlns="http://www.w3.org/2000/svg"
                  >
                    <circle cx="26" cy="26" fill="none" r="25"></circle>
                    <path d="M14.1 27.2l7.1 7.2 16.7-16.8" fill="none"></path>
                  </svg>
                </div>
              </div>
              <p className={`h-6 mt-2 text-error dark:text-molten-error font-label-md text-label-md transition-opacity duration-300 ${isError ? 'opacity-100' : 'opacity-0'}`} id="error-message">
                Invalid Client Key
              </p>
            </div>
            
            <Button
              ref={submitBtnRef}
              onClick={() => handleAuthenticate()}
              isLoading={loading}
              disabled={isSuccess || loading}
              className={`w-full mt-stack-sm ${isShaking ? 'animate-shake' : ''}`}
              icon={isSuccess ? 'check' : 'arrow_forward'}
              id="submit-btn"
            >
              {isSuccess ? 'Success' : (loading ? 'Validating...' : 'Authenticate')}
            </Button>

            {/* TODO: REMOVE THIS BUTTON BEFORE PRODUCTION - FOR TESTING ONLY
            <Button
              variant="ghost"
              onClick={() => triggerSuccess('test_bypass_key_for_development')}
              className="w-full mt-4 !opacity-50 hover:!opacity-100 font-label-md py-2"
            >
              Bypass Auth (Test Mode)
            </Button>
            */}
          </div>
        </div>
      </main>

      {/* Footer Identity */}
      <footer className="fixed bottom-0 w-full flex justify-between items-center px-margin-desktop py-stack-md font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted opacity-60 z-10 animate-stagger-3">
        <span>© 2026 Dev Client. Enterprise-Grade Security.</span>
        <div className="flex gap-gutter">
          <span className="hover:text-primary dark:hover:text-molten-primary cursor-pointer transition-colors">Privacy</span>
          <span className="hover:text-primary dark:hover:text-molten-primary cursor-pointer transition-colors">Status</span>
        </div>
      </footer>
    </div>
  );
};

export default Login;

