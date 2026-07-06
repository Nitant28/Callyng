import CampaignCard from './CampaignCard';
import CampaignSkeleton from './CampaignSkeleton';
import CampaignEmpty from './CampaignEmpty';
import './CampaignGrid.css';

const CampaignGrid = ({ campaigns, loading, botNameById, onOpen, activeTab }) => {
  if (loading) {
    return (
      <div className="cmp-grid">
        {Array.from({ length: 6 }).map((_, i) => (
          <CampaignSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (!campaigns.length) {
    return <CampaignEmpty activeTab={activeTab} />;
  }

  return (
    <div className="cmp-grid">
      {campaigns.map((campaign) => (
        <CampaignCard
          key={campaign.id}
          campaign={campaign}
          voiceAgentName={botNameById?.[campaign.botConfigId]}
          onOpen={() => onOpen(campaign)}
        />
      ))}
    </div>
  );
};

export default CampaignGrid;
