import { useMemo } from 'react';
import { useCampaignWorkspace } from '../../../contexts/CampaignWorkspaceContext';
import StatsBar from '../../../components/client/StatsBar';
import Timeline from '../CampaignDetail/components/Timeline';
import './OverviewTab.css';

const OverviewTab = () => {
  const { campaign, loading } = useCampaignWorkspace();

  const stats = useMemo(() => {
    if (!campaign) return [];
    return [
      { key: 'interested', label: 'Interested', value: campaign.interested_leads },
      { key: 'not_interested', label: 'Not Interested', value: campaign.not_interested_leads },
      { key: 'busy', label: 'Busy', value: campaign.busy_leads },
      { key: 'pending', label: 'Pending', value: campaign.pending_leads },
      { key: 'failed', label: 'Failed', value: campaign.failed_leads },
      { key: 'conversion', label: 'Conversion', value: campaign.conversion_rate, format: 'pct' },
      { key: 'credits', label: 'Credits Used', value: campaign.budget_used_credits, format: 'credits' },
    ];
  }, [campaign]);

  if (!loading && !campaign) {
    return <p className="cw-tab-empty">Campaign not found.</p>;
  }

  return (
    <div className="cw-overview">
      <StatsBar items={stats} loading={loading} />
      {!loading && campaign && <Timeline campaign={campaign} />}
    </div>
  );
};

export default OverviewTab;
