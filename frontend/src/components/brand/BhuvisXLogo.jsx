import './BhuvisXLogo.css';

/**
 * Official BhuvisX wordmark — "Bhuvis" + blue "X".
 * Crisp vector-style typography (no bitmap plate / no stretch).
 * variant: "dark" for light surfaces, "light" for dark sidebar.
 */
const BhuvisXLogo = ({ variant = 'dark', size = 'md', className = '' }) => (
  <span
    className={`bhuvisx-logo bhuvisx-logo--${variant} bhuvisx-logo--${size} ${className}`.trim()}
    role="img"
    aria-label="BhuvisX"
  >
    <span className="bhuvisx-logo__text">Bhuvis</span>
    <span className="bhuvisx-logo__x" aria-hidden="true">X</span>
  </span>
);

export default BhuvisXLogo;
