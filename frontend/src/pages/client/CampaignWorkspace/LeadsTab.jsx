import { useSearchParams } from 'react-router-dom';
import { useCampaignWorkspace } from '../../../contexts/CampaignWorkspaceContext';
import CampaignAnalyticsRow from '../../../components/client/CampaignAnalyticsRow';
import CampaignLeadSheet from '../CampaignDetail/components/CampaignLeadSheet';

const FILTER_MAP = {
  interested: 'interested',
  pending: 'pending',
  calling: 'calling',
  failed: 'failed',
  completed: 'completed',
  callbacks: 'callbacks',
};

const LeadsTab = () => {
  const { campaignId, campaign, loading, refreshCampaign, leadSearch } = useCampaignWorkspace();
  const [searchParams] = useSearchParams();
  const statusParam = searchParams.get('status');
  const initialFilter = FILTER_MAP[statusParam] || 'all';

  if (!campaign) return null;

  return (
    <>
      <CampaignAnalyticsRow campaign={campaign} loading={loading} />
      <CampaignLeadSheet
        campaignId={campaignId}
        campaignName={campaign.name}
        campaignStatus={campaign.status}
        initialFilter={initialFilter}
        externalSearch={leadSearch}
        onLeadsChanged={refreshCampaign}
      />
    </>
  );
};

export default LeadsTab;
