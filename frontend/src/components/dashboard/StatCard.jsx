import './Dashboard.css';

export const formatCredits = (value) => {
  if (value == null) return null;
  return new Intl.NumberFormat('en-IN', {
    maximumFractionDigits: 0,
  }).format(value);
};

const StatCard = ({
  icon,
  iconTone = 'blue',
  title,
  value,
  subtitle,
  loading,
  className = '',
}) => {
  if (loading) {
    return (
      <div className={`stat-card stat-card--skeleton ${className}`}>
        <div className="stat-card__skeleton-row">
          <div className="stat-card__skeleton stat-card__skeleton--icon ds-shimmer" />
          <div className="stat-card__skeleton stat-card__skeleton--title ds-shimmer" />
        </div>
        <div className="stat-card__skeleton stat-card__skeleton--value ds-shimmer" />
        <div className="stat-card__skeleton stat-card__skeleton--sub ds-shimmer" />
      </div>
    );
  }

  return (
    <div className={`stat-card ds-content-loaded ${className}`}>
      <div className="stat-card__top">
        <div className="stat-card__title-row">
          <div className={`stat-card__icon-wrap stat-card__icon-wrap--${iconTone}`}>
            <span className="material-symbols-outlined stat-card__icon">{icon}</span>
          </div>
          <span className="stat-card__title">{title}</span>
        </div>
      </div>
      <div className="stat-card__value">{value ?? '0'}</div>
      {subtitle && <p className="stat-card__subtitle">{subtitle}</p>}
    </div>
  );
};

export default StatCard;
