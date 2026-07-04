import { useNavigate } from 'react-router-dom';
import './Dashboard.css';

const STATUS_LABELS = {
  running: 'Running',
  paused: 'Paused',
  pausing: 'Paused',
  draft: 'Draft',
  completed: 'Completed',
  cancelled: 'Cancelled',
  failed: 'Failed',
};

const formatDate = (iso) => {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return '';
  }
};

const formatCredits = (value) => {
  if (value == null) return '0';
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(value);
};

const CampaignSkeleton = () => (
  <>
    {[1, 2, 3, 4].map((i) => (
      <div key={i} className="campaign-row campaign-row--skeleton">
        <div>
          <div className="campaign-row__skeleton-name ds-shimmer" />
          <div className="campaign-row__skeleton-date ds-shimmer" />
        </div>
        <div className="campaign-row__skeleton-badge ds-shimmer" />
        <div className="campaign-row__skeleton-cell ds-shimmer" />
        <div className="campaign-row__skeleton-cell ds-shimmer" />
        <div className="campaign-row__skeleton-cell ds-shimmer" />
      </div>
    ))}
  </>
);

const CampaignTable = ({ campaigns = [], loading, error }) => {
  const navigate = useNavigate();

  return (
    <div className="campaign-panel ds-enter ds-enter-6">
      <div className="campaign-panel__header">
        <h2 className="campaign-panel__title">Campaign Performance</h2>
      </div>

      {error && <p className="campaign-panel__error">{error}</p>}

      <div className="campaign-panel__cols">
        <span className="campaign-panel__col-label">Campaign</span>
        <span className="campaign-panel__col-label">Status</span>
        <span className="campaign-panel__col-label">Total Leads</span>
        <span className="campaign-panel__col-label">Interested</span>
        <span className="campaign-panel__col-label">Credits Used</span>
      </div>

      <div className="campaign-panel__body">
        {loading && <CampaignSkeleton />}

        {!loading && campaigns.length === 0 && !error && (
          <div className="campaign-panel__empty">No campaigns yet.</div>
        )}

        {!loading &&
          campaigns.map((campaign) => (
            <div
              key={campaign.id}
              className="campaign-row ds-content-loaded"
              onClick={() => navigate(`/app/campaigns/${campaign.id}`)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') navigate(`/app/campaigns/${campaign.id}`);
              }}
              role="button"
              tabIndex={0}
            >
              <div>
                <p className="campaign-row__name">{campaign.title}</p>
                <p className="campaign-row__date">{formatDate(campaign.createdAt)}</p>
              </div>
              <div>
                <span className={`campaign-status campaign-status--${campaign.status}`}>
                  {STATUS_LABELS[campaign.status] ?? campaign.status}
                </span>
              </div>
              <span className="campaign-row__cell">{formatCredits(campaign.totalLeads)}</span>
              <span className="campaign-row__cell">
                {campaign.interestedLeads != null ? formatCredits(campaign.interestedLeads) : '—'}
              </span>
              <span className="campaign-row__cell">{formatCredits(campaign.creditsUsed)}</span>
            </div>
          ))}
      </div>
    </div>
  );
};

export default CampaignTable;
