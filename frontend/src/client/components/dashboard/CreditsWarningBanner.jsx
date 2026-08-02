import { useEffect, useState } from 'react';
import './CreditsWarningBanner.css';

const SESSION_KEY = 'av_credits_banner_dismissed';

const CreditsWarningBanner = ({ remainingCredits, threshold = 2000, onRecharge }) => {
  const [dismissed, setDismissed] = useState(() => {
    try {
      return sessionStorage.getItem(SESSION_KEY) === '1';
    } catch {
      return false;
    }
  });

  useEffect(() => {
    if (remainingCredits == null || remainingCredits >= threshold) return;
    try {
      if (sessionStorage.getItem(SESSION_KEY) === '1') setDismissed(true);
    } catch {
      /* ignore */
    }
  }, [remainingCredits, threshold]);

  if (dismissed) return null;
  if (remainingCredits == null || Number(remainingCredits) >= threshold) return null;

  const formatted = Number(remainingCredits).toLocaleString('en-IN', { maximumFractionDigits: 0 });

  const handleDismiss = () => {
    try {
      sessionStorage.setItem(SESSION_KEY, '1');
    } catch {
      /* ignore */
    }
    setDismissed(true);
  };

  return (
    <div className="cl-credits-banner" role="status">
      <div className="cl-credits-banner__accent" aria-hidden />
      <div className="cl-credits-banner__icon">
        <span className="material-symbols-outlined">warning</span>
      </div>
      <div className="cl-credits-banner__body">
        <div className="cl-credits-banner__title">Low credits remaining</div>
        <div className="cl-credits-banner__text">
          You have <strong>₹{formatted}</strong> credits left. Recharge to keep campaigns running without interruption.
        </div>
      </div>
      <div className="cl-credits-banner__actions">
        <button type="button" className="cl-btn cl-btn--sm cl-credits-banner__cta" onClick={onRecharge}>
          Recharge
        </button>
        <button
          type="button"
          className="cl-credits-banner__close"
          onClick={handleDismiss}
          aria-label="Dismiss payment reminder"
        >
          <span className="material-symbols-outlined">close</span>
        </button>
      </div>
    </div>
  );
};

export default CreditsWarningBanner;
