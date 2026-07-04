import { useMemo } from 'react';
import { buildDashboardKpis } from '../../../utils/dashboardKpis';
import StatCard from './StatCard';
import AnalyticsChart from './AnalyticsChart';
import LiveActivityFeed from './LiveActivityFeed';
import './DashboardGrid.css';

const sum = (campaigns, field) =>
  (campaigns ?? []).reduce((s, c) => s + (c[field] ?? 0), 0);

const DashboardGrid = ({
  credits,
  campaigns,
  calls,
  loading,
  error,
}) => {
  const kpis = useMemo(
    () => buildDashboardKpis(credits, campaigns, calls),
    [credits, campaigns, calls],
  );
  const creditsUsed = sum(campaigns, 'creditsUsed');
  const interested = kpis.leads.qualified;
  const liveCalls = kpis.concurrent.live ?? 0;

  return (
    <div className="cd-grid">
      {(error?.credits || error?.campaigns) && (
        <div className="cd-grid__error">
          {[error.credits, error.campaigns].filter(Boolean).join(' ')}
        </div>
      )}

      <section className="dashboard-stats">
        <StatCard
          title="Credits Remaining"
          icon="account_balance_wallet"
          prefix="₹"
          numericValue={kpis.credits.value}
          loading={loading}
        />
        <StatCard
          title="Interested Leads"
          icon="thumb_up"
          numericValue={interested}
          loading={loading}
        />
        <StatCard
          title="Running Campaigns"
          icon="campaign"
          numericValue={kpis.campaigns.running}
          loading={loading}
        />
        <StatCard
          title="Credits Used"
          icon="payments"
          prefix="₹"
          numericValue={creditsUsed}
          loading={loading}
        />
        <StatCard
          title="Live Calls"
          icon="call"
          numericValue={liveCalls}
          loading={loading}
        />
      </section>

      <section className="cd-grid__analytics-row">
        <AnalyticsChart calls={calls} loading={loading} />
        <LiveActivityFeed calls={calls} campaigns={campaigns} loading={loading} error={error?.calls} />
      </section>
    </div>
  );
};

export default DashboardGrid;
