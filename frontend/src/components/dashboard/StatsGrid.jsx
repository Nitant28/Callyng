import StatCard, { formatCredits } from './StatCard';
import { countActiveCampaigns } from '../../utils/dashboardCalculations';
import './Dashboard.css';

/** Sum authoritative per-campaign counters from backend rows. */
const sumCampaignField = (campaigns, field) => {
  if (!Array.isArray(campaigns)) return 0;
  return campaigns.reduce((sum, c) => sum + (c[field] ?? 0), 0);
};

const StatsGrid = ({ credits, campaigns = [], loading, error }) => {
  const balance = credits?.balanceCredits ?? null;
  const activeCount = countActiveCampaigns(campaigns);
  const totalLeads = sumCampaignField(campaigns, 'totalLeads');
  const liveCalls = sumCampaignField(campaigns, 'callingLeads');
  const completedLeads = sumCampaignField(campaigns, 'completedLeads');

  return (
    <section className="dashboard-stats">
      {(error?.credits || error?.campaigns) && (
        <div className="dashboard-stats__error">
          {[error.credits, error.campaigns].filter(Boolean).join(' ')}
        </div>
      )}

      <StatCard
        className="ds-enter ds-enter-2"
        icon="account_balance_wallet"
        iconTone="blue"
        title="Remaining Credits"
        value={formatCredits(balance)}
        subtitle="Available balance"
        loading={loading}
      />

      <StatCard
        className="ds-enter ds-enter-3"
        icon="campaign"
        iconTone="purple"
        title="Active Campaigns"
        value={loading ? null : String(activeCount)}
        subtitle="Currently running"
        loading={loading}
      />

      <StatCard
        className="ds-enter ds-enter-4"
        icon="groups"
        iconTone="green"
        title="Total Leads"
        value={loading ? null : formatCredits(totalLeads)}
        subtitle="Across all campaigns"
        loading={loading}
      />

      <StatCard
        className="ds-enter ds-enter-5"
        icon="phone_in_talk"
        iconTone="teal"
        title="Live Calls"
        value={loading ? null : formatCredits(liveCalls)}
        subtitle="In progress now"
        loading={loading}
      />

      <StatCard
        className="ds-enter ds-enter-6"
        icon="task_alt"
        iconTone="orange"
        title="Completed Leads"
        value={loading ? null : formatCredits(completedLeads)}
        subtitle="Terminal outcomes"
        loading={loading}
      />
    </section>
  );
};

export default StatsGrid;
