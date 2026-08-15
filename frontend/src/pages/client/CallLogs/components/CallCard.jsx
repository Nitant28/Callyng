import { formatCallCost, formatCallDuration, formatCallTime, getInitials } from '../../../../utils/callLogsHelpers';
import StatusBadge from './StatusBadge';
import './CallCard.css';

const CallCard = ({ call, campaignName, selected, onClick }) => (
  <button
    type="button"
    className={`cl-card ${selected ? 'cl-card--selected' : ''}`}
    onClick={() => onClick(call)}
  >
    <div className="cl-card__avatar">{getInitials(call.leadName)}</div>
    <div className="cl-card__body">
      <div className="cl-card__row">
        <span className="cl-card__name">{call.leadName}</span>
        <span className="cl-card__time">{formatCallTime(call.createdAt)}</span>
      </div>
      <p className="cl-card__campaign">{campaignName || 'Campaign'}</p>
      <div className="cl-card__meta">
        <span className="cl-card__duration">
          <span className="material-symbols-outlined">schedule</span>
          {formatCallDuration(call.durationSeconds)}
        </span>
        <span className="cl-card__cost">
          <span className="material-symbols-outlined">payments</span>
          {formatCallCost(call.creditsCharged ?? call.credits_charged, { inProgress: call.inProgress })}
        </span>
        <StatusBadge outcome={call.outcome} inProgress={call.inProgress} />
      </div>
    </div>
    <span className="material-symbols-outlined cl-card__chevron">chevron_right</span>
  </button>
);

export default CallCard;
