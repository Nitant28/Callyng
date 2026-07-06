import './CampaignSkeleton.css';

const CampaignSkeleton = () => (
  <div className="cmp-skeleton">
    <div className="ds-shimmer cmp-skeleton__line" style={{ width: '60%', height: 18 }} />
    <div className="ds-shimmer cmp-skeleton__line" style={{ width: '40%', height: 14 }} />
    <div className="ds-shimmer" style={{ height: 60, borderRadius: 12 }} />
    <div className="ds-shimmer" style={{ height: 6, borderRadius: 999 }} />
    <div className="ds-shimmer" style={{ height: 36, borderRadius: 12 }} />
  </div>
);

export default CampaignSkeleton;
