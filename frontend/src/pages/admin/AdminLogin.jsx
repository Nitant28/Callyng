import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTheme } from '../../hooks/useTheme';
import { useAdminAuth } from '../../contexts/AdminAuthContext';
import adminApi from '../../api/admin';
import './AdminLogin.css';

export default function AdminLogin() {
  const { theme, toggleTheme } = useTheme();
  const { login, logout } = useAdminAuth();
  const navigate = useNavigate();
  const [status, setStatus] = useState('idle'); // 'idle', 'authenticating', 'error'
  const [secretKey, setSecretKey] = useState('');
  const secretInputRef = useRef(null);
  const cardRef = useRef(null);

  useEffect(() => {
    if (secretInputRef.current) {
      secretInputRef.current.focus();
    }
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if ((status !== 'idle' && status !== 'error') || !secretKey) return;
    
    setStatus('authenticating');

    try {
      // Set the key in Context
      login(secretKey);
      
      // Test the key against health
      await adminApi.get('/internal/health');
      
      // If success, navigate to admin dashboard
      navigate('/admin');
    } catch (error) {
      // If unauthorized or error, remove the key and show error
      logout();
      setStatus('error');
      
      // Trigger error shake animation by toggling class
      if (cardRef.current) {
        cardRef.current.classList.remove('error-shake');
        void cardRef.current.offsetWidth; // force reflow
        cardRef.current.classList.add('error-shake');
      }
    }
  };

  const handleRetry = (e) => {
    if (e) e.preventDefault();
    setStatus('idle');
    if (secretInputRef.current) {
      secretInputRef.current.focus();
      secretInputRef.current.select();
    }
  };

  return (
    <div className="bg-arctic-bg dark:bg-molten-bg text-arctic-text dark:text-molten-text min-h-screen flex flex-col items-center justify-center relative overflow-hidden theme-transition">
      {/* Theme Toggle */}
      <button 
        onClick={toggleTheme}
        aria-label="Toggle dark mode" 
        className="absolute top-gutter right-gutter p-stack-sm rounded-full bg-arctic-surface dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] shadow-lg hover:-translate-y-px transition-all z-50 theme-transition"
      >
        {theme === 'dark' ? (
          <span className="material-symbols-outlined text-molten-primary block">light_mode</span>
        ) : (
          <span className="material-symbols-outlined text-primary block">dark_mode</span>
        )}
      </button>

      {/* Main Content Canvas */}
      <main className="relative z-10 w-full max-w-md px-margin-mobile md:px-0 state-transition">
        <div className="text-center mb-stack-lg">
          <h1 className="font-headline-xl text-headline-xl text-primary dark:text-molten-primary mb-stack-sm tracking-tight drop-shadow-sm theme-transition">
            Aakashvani Admin
          </h1>
          <p className="font-body-md text-body-md text-arctic-text-muted dark:text-molten-text-muted theme-transition">
            {status === 'idle' && 'Enter administrative credentials to proceed.'}
            {status === 'authenticating' && 'Verifying bypass protocols...'}
            {status === 'error' && 'Access Denied: Gateway Protocol Violation.'}
          </p>
        </div>

        <div ref={cardRef} className={`bg-arctic-surface dark:bg-molten-surface p-stack-lg rounded-lg shadow-xl dark:shadow-none dark:border dark:border-[#2A345E] relative z-20 state-transition theme-transition ${status === 'error' ? 'error-shake' : ''}`}>
          {/* Top Error Indicator */}
          {status === 'error' && (
            <div className="absolute top-0 left-0 w-full h-1 bg-arctic-error dark:bg-molten-error"></div>
          )}

          <form onSubmit={handleSubmit} className="flex flex-col gap-stack-md">
            <div className="space-y-2">
              <label htmlFor="secretKey" className="sr-only">Admin Secret Key</label>
              <div className="relative group">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <span 
                    className={`material-symbols-outlined transition-colors theme-transition ${
                      status === 'error' 
                        ? 'text-arctic-error dark:text-molten-error'
                        : 'text-outline-variant dark:text-molten-text-muted group-focus-within:text-primary dark:group-focus-within:text-molten-primary'
                    }`} 
                  >
                    key
                  </span>
                </div>
                <input 
                  ref={secretInputRef}
                  id="secretKey" 
                  type="password" 
                  value={secretKey}
                  onChange={(e) => {
                    setSecretKey(e.target.value);
                    if (status === 'error') {
                      setStatus('idle');
                    }
                  }}
                  placeholder="Admin Secret Key" 
                  autoComplete="off" 
                  disabled={status === 'authenticating'}
                  className={`w-full pl-10 pr-4 py-3 bg-transparent border rounded-lg font-body-md text-body-md focus:outline-none focus:ring-2 focus:border-transparent transition-all theme-transition placeholder:text-arctic-text-muted dark:placeholder:text-molten-text-muted ${
                    status === 'authenticating' ? 'opacity-50 pointer-events-none' : ''
                  } ${
                    status === 'error' 
                      ? 'border-arctic-error dark:border-molten-error ring-arctic-error dark:ring-molten-error'
                      : 'border-outline-variant dark:border-[#2A345E] text-arctic-text dark:text-molten-text focus:ring-primary dark:focus:ring-molten-primary'
                  }`}
                />
              </div>

              {/* Error Message */}
              {status === 'error' && (
                <div className="flex items-center gap-1.5 mt-2 px-1">
                  <span className="material-symbols-outlined text-sm text-arctic-error dark:text-molten-error" style={{ fontSize: '14px' }}>error</span>
                  <p className="font-body-sm text-body-sm font-semibold theme-transition text-arctic-error dark:text-molten-error">
                    Invalid Secret Key. Access Denied.
                  </p>
                </div>
              )}
            </div>

            {/* Idle State Button */}
            {status === 'idle' && (
              <div>
                <button type="submit" className="w-full py-3 bg-primary dark:bg-molten-primary text-white dark:text-molten-bg font-label-md text-label-md rounded-lg btn-tactile hover:brightness-110 transition-all duration-200 hover:-translate-y-px active:translate-y-0 flex items-center justify-center gap-2 theme-transition">
                  Authenticate
                  <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
                </button>
              </div>
            )}

            {/* Authenticating State Button */}
            {status === 'authenticating' && (
              <div>
                <div className="w-full bg-primary dark:bg-molten-primary py-3 rounded-lg flex flex-col items-center justify-center relative overflow-hidden group shadow-[inset_0_1px_0_rgba(255,255,255,0.2)] theme-transition">
                  <div className="flex items-center gap-3 z-10">
                    <span className="material-symbols-outlined loader-spin text-white dark:text-molten-bg font-bold text-[18px]">progress_activity</span>
                    <span className="font-label-md text-label-md text-white dark:text-molten-bg tracking-wide">Validating Credentials...</span>
                  </div>
                  <div className="absolute bottom-0 left-0 h-1 bg-white/20 dark:bg-molten-bg/20 w-full">
                    <div className="h-full bg-white dark:bg-molten-bg w-1/3 progress-shimmer"></div>
                  </div>
                </div>
              </div>
            )}

            {/* Error State Button */}
            {status === 'error' && (
              <div>
                <button type="button" onClick={handleRetry} className="w-full py-3 bg-arctic-error dark:bg-molten-error text-white font-label-md text-label-md rounded-lg active:scale-[0.98] transition-all hover:brightness-110 shadow-lg flex items-center justify-center gap-2 group theme-transition">
                  <span>Retry Authentication</span>
                  <span className="material-symbols-outlined text-md group-hover:translate-x-1 transition-transform">login</span>
                </button>
              </div>
            )}
          </form>

          {/* Footer links in error state */}
          {status === 'error' && (
            <div className="mt-8 pt-6 border-t border-outline-variant dark:border-[#2A345E] flex flex-col items-center gap-4">
              <p className="font-label-sm text-label-sm flex items-center gap-2 theme-transition text-arctic-text-muted dark:text-molten-text-muted">
                <span className="material-symbols-outlined text-sm" style={{ fontSize: '16px' }}>info</span>
                Forgot your secret key? Contact System Architect.
              </p>
              <a href="#" className="font-label-sm text-label-sm hover:underline transition-all theme-transition text-primary dark:text-molten-primary">
                Back to Standard Login
              </a>
            </div>
          )}
        </div>
      </main>

      {/* Animated Waveform Background */}
      <div className="absolute top-0 left-0 w-full h-64 overflow-hidden pointer-events-none opacity-20 dark:opacity-10 z-0">
        <svg className="w-[200%] h-full waveform-path theme-transition text-primary dark:text-molten-primary" preserveAspectRatio="none" style={{ fill: 'currentColor' }} viewBox="0 0 1200 120">
          <path d="M0,0V46.29c47.79,22.2,103.59,32.17,158,28,70.36-5.37,136.33-33.31,206.8-37.5C438.64,32.43,512.34,53.67,583,72.05c69.27,18,138.3,24.88,209.4,13.08,36.15-6,69.85-17.84,104.45-29.34C989.49,25,1113-14.29,1200,52.47V0Z" opacity=".25"></path>
          <path d="M0,0V15.81C13,36.92,27.64,56.86,47.69,72.05,99.41,111.27,165,111,224.58,91.58c31.15-10.15,60.09-26.07,89.67-39.8,40.92-19,84.73-46,130.83-49.67,36.26-2.85,70.9,9.42,98.6,31.56,31.77,25.39,62.32,62,103.63,73,40.44,10.79,81.35-6.69,119.13-24.28s75.16-39,116.92-43.05c59.73-5.85,113.28,22.88,168.9,38.84,30.2,8.66,59,6.17,87.09-7.5V0Z" opacity=".5"></path>
          <path d="M0,0V5.63C149.93,59,314.09,71.32,475.83,42.57c43-7.64,84.23-20.12,127.61-26.46,59-8.63,112.48,12.24,165.56,35.4C827.93,77.22,886,95.24,951.2,90c86.53-7,172.46-45.71,248.8-84.81V0Z"></path>
          <path d="M1200,0V46.29c47.79,22.2,103.59,32.17,158,28,70.36-5.37,136.33-33.31,206.8-37.5C1638.64,32.43,1712.34,53.67,1783,72.05c69.27,18,138.3,24.88,209.4,13.08,36.15-6,69.85-17.84,104.45-29.34C2189.49,25,2313-14.29,2400,52.47V0Z" opacity=".25"></path>
          <path d="M1200,0V15.81C1213,36.92,1227.64,56.86,1247.69,72.05,1299.41,111.27,1365,111,1424.58,91.58c31.15-10.15,60.09-26.07,89.67-39.8,40.92-19,84.73-46,130.83-49.67,36.26-2.85,70.9,9.42,98.6,31.56,31.77,25.39,62.32,62,103.63,73,40.44,10.79,81.35-6.69,119.13-24.28s75.16-39,116.92-43.05c59.73-5.85,113.28,22.88,168.9,38.84,30.2,8.66,59,6.17,87.09-7.5V0Z" opacity=".5"></path>
          <path d="M1200,0V5.63C1349.93,59,1514.09,71.32,1675.83,42.57c43-7.64,84.23-20.12,127.61-26.46,59-8.63,112.48,12.24,165.56,35.4C2027.93,77.22,2086,95.24,2151.2,90c86.53-7,172.46-45.71,248.8-84.81V0Z"></path>
        </svg>
      </div>
    </div>
  );
}
