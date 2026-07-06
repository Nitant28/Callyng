import './StatCard.css';

export const formatNumber = (value) => {
  if (value == null) return null;
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(value);
};

const StatCard = ({
  title,
  icon,
  prefix = null,
  numericValue = null,
  loading,
}) => {
  if (loading) {
    return (
      <div className="cd-stat cd-stat--skeleton ui-base-card">
        <div className="ds-shimmer cd-stat__skel-label" />
        <div className="ds-shimmer cd-stat__skel-value" />
      </div>
    );
  }

  return (
    <div className="cd-stat ui-base-card">
      <div className="cd-stat__head">
        {icon && (
          <span className="material-symbols-outlined cd-stat__icon" aria-hidden>
            {icon}
          </span>
        )}
        <p className="cd-stat__label">{title}</p>
      </div>
      <div className="cd-stat__metric">
        {prefix && <span className="cd-stat__prefix">{prefix}</span>}
        <span className="cd-stat__value">
          {numericValue != null ? formatNumber(numericValue) : '—'}
        </span>
      </div>
    </div>
  );
};

export default StatCard;
