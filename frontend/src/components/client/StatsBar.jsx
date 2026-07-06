import './StatsBar.css';

const fmt = (n) => (n ?? 0).toLocaleString('en-IN');
const fmtPct = (n) => (n == null ? '—' : `${n}%`);
const fmtCredits = (n) => (n == null ? '—' : `₹${fmt(n)}`);

const StatsBar = ({ items = [], loading = false }) => {
  if (loading) {
    return (
      <div className="cw-stats cw-stats--loading">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="cw-stats__cell cw-stats__cell--skeleton" />
        ))}
      </div>
    );
  }

  return (
    <div className="cw-stats">
      {items.map(({ key, label, value, format }) => (
        <div key={key} className="cw-stats__cell">
          <span className="cw-stats__label">{label}</span>
          <span className="cw-stats__value">
            {format === 'pct' ? fmtPct(value) : format === 'credits' ? fmtCredits(value) : fmt(value)}
          </span>
        </div>
      ))}
    </div>
  );
};

export default StatsBar;
