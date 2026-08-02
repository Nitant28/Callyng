import './DashboardInterestedLeads.css';

const isInterested = (outcome) => {
  const o = (outcome || '').toString();
  return o === 'Interested' || (o.includes('Interest') && o !== 'Not_Interested');
};

const DashboardInterestedLeads = ({ calls = [], onOpenLead }) => {
  const rows = (calls || []).filter((c) => isInterested(c.outcome)).slice(0, 12);

  return (
    <section className="cl-interested-panel">
      <div className="cl-interested-panel__header">
        <h3 className="cl-card-title">Interested Leads</h3>
        <span className="cl-interested-panel__count">{rows.length} shown</span>
      </div>
      <div className="cl-interested-panel__table-wrap">
        <table className="cl-lead-table cl-interested-panel__table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Phone</th>
              <th>Time</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={3} className="cl-interested-panel__empty">No interested leads yet.</td>
              </tr>
            ) : (
              rows.map((call) => (
                <tr
                  key={call.session_call_id || call.id}
                  onClick={() => onOpenLead?.(call)}
                >
                  <td className="font-semibold text-primary">{call.name || call.lead_name || '—'}</td>
                  <td className="font-mono">{call.phone || call.lead_phone || '—'}</td>
                  <td>
                    {call.ended_at || call.started_at
                      ? new Date(call.ended_at || call.started_at).toLocaleString('en-IN', {
                          month: 'short',
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })
                      : '—'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
};

export default DashboardInterestedLeads;
