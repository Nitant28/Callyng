import { Badge } from '../../../../components/enterprise';
import './DetailHeader.css';

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
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
};

const DetailHeader = ({
  campaign,
  clientName,
  creditsRemaining,
  isPausing,
  isReleasingStuck,
  onToggleState,
  onCancel,
  onReleaseStuck,
}) => {
  const status = STATUS_MAP[campaign.status] ?? { label: campaign.status, tone: 'neutral' };
  const showRelease =
    campaign.calling_leads > 0 && ['running', 'pausing', 'paused'].includes(campaign.status);
  const canControl = campaign.status !== 'cancelled' && campaign.status !== 'completed';

  return (
    <header className="cdet-header">
      <div className="cdet-header__main">
        <div className="cdet-header__title-row">
          <h1>{campaign.name}</h1>
          <Badge tone={status.tone}>{status.label}</Badge>
        </div>
        <p className="cdet-header__subtitle">
          ₹{(campaign.budget_credits ?? 0).toLocaleString('en-IN')} budget
          · {campaign.bot_config?.name || 'Voice agent'}
          · Created {fmtDate(campaign.created_at)}
        </p>
      </div>

      <div className="cdet-header__actions">
        {showRelease && (
          <button
            type="button"
            className="cdet-header__btn cdet-header__btn--warn"
            onClick={onReleaseStuck}
            disabled={isReleasingStuck}
          >
            <span className="material-symbols-outlined">lock_open</span>
            Release stuck leads
          </button>
        )}
        {canControl && (
          <button type="button" className="cdet-header__btn" onClick={onToggleState}>
            {campaign.status === 'running' ? 'Pause Campaign' : 'Start Campaign'}
          </button>
        )}
        {campaign.status === 'paused' && (
          <button type="button" className="cdet-header__btn cdet-header__btn--danger" onClick={onCancel}>
            Cancel & Refund
          </button>
        )}
      </div>

      {isPausing && (
        <p className="cdet-header__pausing">
          Waiting for {campaign.calling_leads} active call{campaign.calling_leads !== 1 ? 's' : ''} to finish…
        </p>
      )}
    </header>
  );
};

export default DetailHeader;
