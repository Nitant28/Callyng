import './SwarnaLogo.css';

/**
 * Swarna wordmark — emerald on white, cream on forest sidebar.
 */
const SwarnaLogo = ({ variant = 'dark', size = 'md', className = '' }) => (
  <span
    className={`swarna-logo swarna-logo--${variant} swarna-logo--${size} ${className}`.trim()}
    role="img"
    aria-label="Swarna"
  >
    <span className="swarna-logo__mark" aria-hidden="true">
      S
    </span>
    <span className="swarna-logo__text">Swarna</span>
  </span>
);

export default SwarnaLogo;
