import './LeadsTable.css';

const OUTCOME_LABELS = {
  Interested: 'Connected',
  Not_Interested: 'Not Interested',
  Callback_Requested: 'Callback',
  Carrier_Failed: 'Carrier Failed',
  Early_Disconnect: 'Hung up early',
  Max_Attempts_Reached: 'Max Attempts',
  Campaign_Cancelled: 'Cancelled',
};

const friendlyOutcome = (outcome, fallback = 'Unknown') => {
  const key = (outcome || '').toString().trim();
  if (!key) return fallback;
  return OUTCOME_LABELS[key] || key.replace(/_/g, ' ');
};

const formatCallbackTiming = (nextAt) => {
  if (!nextAt) return 'Retry scheduled';
  const target = new Date(nextAt);
  const diffMs = target - Date.now();
  if (diffMs <= 0) return 'Retry due';
  const mins = Math.ceil(diffMs / 60000);
  if (mins < 60) return `Retry in ${mins} min`;
  const hours = Math.ceil(mins / 60);
  if (hours < 48) return `Retry in ${hours}h`;
  return target.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
};

const initials = (name) => {
  if (!name) return '?';
  return name.split(/\s+/).map((w) => w[0]).join('').toUpperCase().slice(0, 2);
};

const fmtDuration = (sec) => {
  if (sec == null || sec <= 0) return '—';
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
};

const fmtRelative = (iso) => {
  if (!iso) return '—';
  const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return 'Just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
};

const StatusBadge = ({ lead }) => {
  const outcome = (lead.outcome || '').toString();
  let tone = 'neutral';
  let line1 = (lead.status || 'unknown').replace(/_/g, ' ');
  let line2 = null;

  if (lead.status === 'completed') {
    tone = outcome === 'Interested' ? 'success' : 'neutral';
    line1 = friendlyOutcome(outcome, 'Completed');
  } else if (lead.status === 'failed') {
    tone = 'danger';
    line1 = friendlyOutcome(outcome, 'Failed');
    line2 = 'Call failed';
  } else if (lead.status === 'calling') {
    tone = 'warning';
    line1 = 'On live call';
    line2 = 'In progress';
  } else if (lead.status === 'callback_scheduled') {
    tone = 'info';
    line1 = friendlyOutcome(outcome, 'Callback');
    line2 = formatCallbackTiming(lead.next_attempt_at || lead.scheduled_callback_at);
  } else if (lead.status === 'pending' && (lead.attempts || 0) > 0) {
    tone = 'warning';
    line1 = 'Retry queued';
    line2 = `Attempt ${lead.attempts}/${lead.max_attempts || 3}`;
  } else if (lead.status === 'pending') {
    line1 = 'Awaiting first call';
    line2 = 'Queued';
  }

  return (
    <span className={`cdet-leads__badge cdet-leads__badge--${tone}`}>
      <span className="cdet-leads__badge-dot" />
      <span className="cdet-leads__badge-text">
        <span>{line1}</span>
        {line2 && <small>{line2}</small>}
      </span>
    </span>
  );
};

const LeadsTable = ({
  leads,
  leadsLoading,
  totalLeadsCount,
  campaign,
  campaignName,
  leadsSearch,
  onSearchChange,
  leadsOffset,
  leadsLimit,
  onPrevPage,
  onNextPage,
  canAddLead,
  onAddLead,
  onOpenLead,
  onEditLead,
  onDeleteLead,
}) => {
  const isCampaignLocked = ['running', 'pausing'].includes(campaign?.status);

  return (
    <div className="cdet-leads">
      <div className="cdet-leads__toolbar">
        <div className="cdet-leads__toolbar-left">
          <h3>Active Leads ({totalLeadsCount.toLocaleString('en-IN')})</h3>
          {canAddLead && (
            <button type="button" className="cdet-leads__add" onClick={onAddLead}>
              <span className="material-symbols-outlined">person_add</span>
              Add Contact
            </button>
          )}
        </div>
        <div className="cdet-leads__search">
          <span className="material-symbols-outlined">search</span>
          <input
            type="search"
            placeholder="Search leads…"
            value={leadsSearch}
            onChange={(e) => onSearchChange(e.target.value)}
          />
        </div>
      </div>

      <div className="cdet-leads__table-wrap">
        <table className="cdet-leads__table">
          <thead>
            <tr>
              <th>Lead</th>
              <th>Phone</th>
              <th>Campaign</th>
              <th>Status</th>
              <th>Attempts</th>
              <th>Last Call</th>
              <th>Duration</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {leadsLoading ? (
              <tr>
                <td colSpan={8} className="cdet-leads__empty">Loading leads…</td>
              </tr>
            ) : leads.length === 0 ? (
              <tr>
                <td colSpan={8} className="cdet-leads__empty">
                  <span className="material-symbols-outlined">person_off</span>
                  <p>No leads found</p>
                  <small>Adjust search or import a CSV to get started.</small>
                </td>
              </tr>
            ) : (
              leads.map((lead) => {
                const isLeadLocked = lead.status === 'calling';
                const locked = isCampaignLocked || isLeadLocked;

                return (
                  <tr key={lead.id} onClick={() => onOpenLead(lead)} className="cdet-leads__row">
                    <td>
                      <div className="cdet-leads__identity">
                        <span className="cdet-leads__avatar">{initials(lead.name)}</span>
                        <span className="cdet-leads__name">{lead.name || '—'}</span>
                      </div>
                    </td>
                    <td className="cdet-leads__phone">{lead.phone}</td>
                    <td className="cdet-leads__muted">{campaignName}</td>
                    <td><StatusBadge lead={lead} /></td>
                    <td className="cdet-leads__num">{lead.attempts || 0}</td>
                    <td className="cdet-leads__muted">
                      {fmtRelative(lead.last_called_at || lead.updated_at)}
                    </td>
                    <td className="cdet-leads__muted">
                      {fmtDuration(lead.last_call_duration_seconds)}
                    </td>
                    <td className="cdet-leads__actions" onClick={(e) => e.stopPropagation()}>
                      {locked ? (
                        <span className="cdet-leads__lock" title="Lead is locked">
                          <span className="material-symbols-outlined">lock</span>
                        </span>
                      ) : (
                        <>
                          <button type="button" onClick={() => onEditLead(lead)} aria-label="Edit">
                            <span className="material-symbols-outlined">edit</span>
                          </button>
                          <button type="button" onClick={() => onDeleteLead(lead.id)} aria-label="Delete">
                            <span className="material-symbols-outlined">delete</span>
                          </button>
                        </>
                      )}
                      <button type="button" className="cdet-leads__view" onClick={() => onOpenLead(lead)}>
                        View
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <footer className="cdet-leads__footer">
        <span>
          Showing {leads.length > 0 ? leadsOffset + 1 : 0}–{Math.min(leadsOffset + leadsLimit, totalLeadsCount)} of{' '}
          {totalLeadsCount}
        </span>
        <div>
          <button type="button" disabled={leadsOffset === 0} onClick={onPrevPage}>Previous</button>
          <button
            type="button"
            disabled={leadsOffset + leadsLimit >= totalLeadsCount}
            onClick={onNextPage}
          >
            Next
          </button>
        </div>
      </footer>
    </div>
  );
};

export default LeadsTable;
