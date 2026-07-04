import { buildDashboardKpis } from '../../../utils/dashboardKpis';
import { formatNumber } from './StatCard';
import './ExecutiveMetrics.css';

const Metric = ({ label, value, sub, tone }) => (
  <div className={`exec-metric exec-metric--${tone || 'neutral'}`}>
    <span className="exec-metric__label">{label}</span>
    <span className="exec-metric__value">{value ?? '—'}</span>
    {sub && <span className="exec-metric__sub">{sub}</span>}
  </div>
);

const ExecutiveMetrics = ({ credits, campaigns, calls, loading }) => {
  const kpis = buildDashboardKpis(credits, campaigns, calls);
  const { executive } = kpis;

  if (loading) {
    return (
      <div className="exec-metrics">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="exec-metric ds-shimmer" style={{ height: 72 }} />
        ))}
      </div>
    );
  }

  return (
    <div className="exec-metrics">
      <Metric
        label="Answer Rate"
        value={executive.answerRate != null ? `${executive.answerRate.toFixed(0)}%` : null}
        sub={executive.answerRate != null ? "From today's calls" : 'Needs call outcomes'}
        tone="blue"
      />
      <Metric
        label="Avg Call Duration"
        value={executive.avgDuration}
        sub={executive.avgDuration ? "Today's average" : 'No durations logged'}
        tone="mint"
      />
      <Metric
        label="Portfolio Health"
        value={executive.healthScore != null ? `${executive.healthScore}%` : null}
        sub={executive.healthScore != null ? 'Across active campaigns' : 'No campaign data'}
        tone="green"
      />
      <Metric
        label="Cost Per Lead"
        value={executive.costPerLead != null ? `₹${formatNumber(executive.costPerLead)}` : null}
        sub={executive.costPerLead != null ? 'From account metrics' : 'Not provided by API'}
        tone="purple"
      />
    </div>
  );
};

export default ExecutiveMetrics;
