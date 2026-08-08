import MetricCard from '../shared/MetricCard';

const DashboardKPIs = ({
  interestedLeads,
  totalLeads,
  runningCampaigns,
  liveCalls,
  creditsUsed,
  remainingCredits,
}) => {
  const remaining = Number.isFinite(Number(remainingCredits)) ? Number(remainingCredits) : 0;

  return (
    <div className="cl-dashboard-kpis cl-mb-section">
      <MetricCard
        label="Remaining Credits"
        value={remaining.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
        icon="account_balance_wallet"
        iconClass="icon-blue"
      />

      <MetricCard
        label="Interested Leads"
        value={Number(interestedLeads || 0).toLocaleString()}
        icon="thumb_up"
        iconClass="icon-green"
      />

      <MetricCard
        label="Total Leads"
        value={Number(totalLeads || 0).toLocaleString()}
        icon="groups"
        iconClass="icon-teal"
      />

      <MetricCard
        label="Live Calls"
        value={Number(liveCalls || 0).toLocaleString()}
        icon="sensors"
        iconClass="icon-purple"
        footer={runningCampaigns > 0 ? `${runningCampaigns} campaign${runningCampaigns === 1 ? '' : 's'} running` : 'No active dialers'}
      />

      <MetricCard
        label="Credits Used"
        value={`${Number(creditsUsed || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`}
        icon="monetization_on"
        iconClass="icon-orange"
      />
    </div>
  );
};

export default DashboardKPIs;
