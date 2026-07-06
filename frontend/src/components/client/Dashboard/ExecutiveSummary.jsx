import { buildExecutiveSummary } from '../../../utils/dashboardKpis';
import { formatNumber } from './StatCard';
import './ExecutiveSummary.css';

const ExecutiveSummary = ({ calls, campaigns, loading }) => {
  const summary = buildExecutiveSummary(calls, campaigns);
  const items = [
    { label: 'Calls Attempted', value: summary.attempted },
    { label: 'Answered', value: summary.answered },
    { label: 'Interested', value: summary.interested },
    { label: 'Converted', value: summary.converted },
    { label: 'Failed', value: summary.failed },
  ];
  const isEmpty = !loading && items.every((i) => i.value === 0);

  return (
    <section className="exec-summary">
      <div className="exec-summary__head">
        <h3>{summary.label}</h3>
        {summary.source === 'calls_today' && (
          <span className="exec-summary__badge">Live sample</span>
        )}
      </div>
      {loading && (
        <div className="exec-summary__grid">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="exec-summary__cell ds-shimmer" style={{ height: 56 }} />
          ))}
        </div>
      )}
      {!loading && isEmpty && (
        <p className="exec-summary__empty">
          No activity yet today. Launch a campaign to begin monitoring AI performance.
        </p>
      )}
      {!loading && !isEmpty && (
        <div className="exec-summary__grid">
          {items.map((item) => (
            <div key={item.label} className="exec-summary__cell">
              <span className="exec-summary__value">{formatNumber(item.value) ?? '0'}</span>
              <span className="exec-summary__label">{item.label}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
};

export default ExecutiveSummary;
