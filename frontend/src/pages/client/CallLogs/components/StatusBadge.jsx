import { outcomeLabel, outcomeTone } from '../../../../utils/callLogsHelpers';
import './StatusBadge.css';

const StatusBadge = ({ outcome, inProgress }) => {
  if (inProgress) {
    return (
      <span className="cl-status cl-status--live">
        <span className="cl-status__pulse" />
        Live
      </span>
    );
  }

  const tone = outcomeTone(outcome);
  const label = outcomeLabel(outcome);
  const isRetry = (outcome || '').toLowerCase().includes('carrier');

  return (
    <span className={`cl-status cl-status--${tone}`}>
      {label}
      {isRetry && <span className="cl-status__sub">Retrying</span>}
    </span>
  );
};

export default StatusBadge;
