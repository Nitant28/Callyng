import { useCampaignWorkspace } from '../../contexts/CampaignWorkspaceContext';
import './CampaignHeader.css';

const STATUS_MAP = {
  running: { label: 'Running', tone: 'success' },
  paused: { label: 'Paused', tone: 'warning' },
  pausing: { label: 'Pausing', tone: 'warning' },
  draft: { label: 'Draft', tone: 'neutral' },
  completed: { label: 'Completed', tone: 'info' },
  cancelled: { label: 'Cancelled', tone: 'danger' },
  failed: { label: 'Failed', tone: 'danger' },
};

const fmtDate = (iso) => {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
};

const fmtCredits = (n) =>
  n == null ? '—' : `₹${new Intl.NumberFormat('en-IN').format(n)}`;

const CampaignHeader = ({ onToggleState }) => {
  const { campaign, isPausing } = useCampaignWorkspace();
  if (!campaign) return null;

  const status = STATUS_MAP[campaign.status] ?? { label: campaign.status, tone: 'neutral' };
  const canToggle = campaign.status !== 'cancelled' && campaign.status !== 'completed';

  return (
    <header className="cw-header cw-header--compact">
      <div className="cw-header__main">
        <div className="cw-header__info">
          <div className="cw-header__title-row">
            <h1 className="cw-header__title">{campaign.name}</h1>
            <span className={`cw-header__status cw-header__status--${status.tone}`}>
              {status.label}
            </span>
          </div>
          <p className="cw-header__meta">
            ID {campaign.id}
            <span aria-hidden>·</span>
            Created {fmtDate(campaign.created_at)}
          </p>
        </div>

        <div className="cw-header__actions">
          {canToggle && (
            <button type="button" className="cw-header__btn" onClick={onToggleState}>
              {campaign.status === 'running' ? 'Pause' : 'Start'}
            </button>
          )}
        </div>
      </div>
    </header>
  );
};

export default CampaignHeader;
