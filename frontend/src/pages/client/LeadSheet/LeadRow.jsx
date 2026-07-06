import LeadStatusBadge from './LeadStatusBadge';
import { leadInitials, fmtDuration, fmtRelative } from './leadUtils';
import './LeadTable.css';

const LeadRow = ({ lead, selected, onToggleSelect, onClick, onEdit, onDelete }) => {
  const locked = lead.status === 'calling';

  return (
    <tr
      className={`ent-table__row--clickable ls-row ${locked ? 'ls-row--calling' : ''}`}
      onClick={() => onClick?.(lead)}
    >
      <td className="ent-table__check" onClick={(e) => e.stopPropagation()}>
        <input
          type="checkbox"
          checked={selected}
          onChange={() => onToggleSelect(lead.id)}
          aria-label={`Select ${lead.name || lead.phone}`}
        />
      </td>
      <td>
        <div className="ls-row__identity">
          <span className="ls-row__avatar">{leadInitials(lead.name)}</span>
          <div className="ls-row__name-block">
            <span className="ls-row__name">{lead.name || '—'}</span>
            {lead.metadata?.email && (
              <span className="ls-row__email">{lead.metadata.email}</span>
            )}
          </div>
        </div>
      </td>
      <td className="ls-row__phone">{lead.phone}</td>
      <td className="ls-row__muted">{lead.campaignName}</td>
      <td><LeadStatusBadge lead={lead} /></td>
      <td className="ls-row__num">{lead.attempts ?? 0}</td>
      <td className="ls-row__muted">{fmtDuration(lead.lastCallDurationSeconds)}</td>
      <td className="ls-row__muted">{fmtRelative(lead.lastCalledAt)}</td>
      <td className="ls-row__actions" onClick={(e) => e.stopPropagation()}>
        <div className="ls-row__actions-inner">
          {!locked && (
            <>
              <button type="button" onClick={() => onEdit?.(lead)} aria-label="Edit">
                <span className="material-symbols-outlined">edit</span>
              </button>
              <button type="button" onClick={() => onDelete?.(lead)} aria-label="Delete">
                <span className="material-symbols-outlined">delete</span>
              </button>
            </>
          )}
          <button type="button" className="ls-row__view" onClick={() => onClick?.(lead)}>
            View
          </button>
        </div>
      </td>
    </tr>
  );
};

export default LeadRow;
