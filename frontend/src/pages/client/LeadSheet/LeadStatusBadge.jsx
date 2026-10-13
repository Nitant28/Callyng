import { getLeadDialState, getLeadCallResult, getLeadInterestState } from './leadUtils';
import './LeadStatusBadge.css';

const DOT = {
  success: '#22c55e',
  warning: '#eab308',
  info: '#10B981',
  danger: '#ef4444',
  neutral: '#94a3b8',
};

const MODES = {
  dial: getLeadDialState,
  result: getLeadCallResult,
  interest: getLeadInterestState,
};

const LeadStatusBadge = ({ lead, mode = 'dial' }) => {
  const display = (MODES[mode] || getLeadDialState)(lead);
  const { tone, label, sub, live } = display;
  return (
    <span className={`ls-badge ls-badge--${tone} ${live ? 'ls-badge--live' : ''}`}>
      <span className="ls-badge__dot" style={{ background: DOT[tone] || DOT.neutral }} />
      <span className="ls-badge__text">
        <span>{label}</span>
        {sub && <small>{sub}</small>}
      </span>
    </span>
  );
};

export default LeadStatusBadge;
