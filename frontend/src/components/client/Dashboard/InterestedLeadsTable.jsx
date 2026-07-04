import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { outcomeLabel } from '../../../utils/callLogsHelpers';
import './InterestedLeadsTable.css';

const InterestedLeadsTable = ({ calls = [], campaigns = [], loading }) => {
  const navigate = useNavigate();

  const rows = useMemo(() => {
    return (calls ?? [])
      .filter((c) => {
        const o = (c.outcome || '').toString();
        return o === 'Interested' || (o.includes('Interest') && o !== 'Not_Interested');
      })
      .slice(0, 10);
  }, [calls]);

  const campaignIdForViewAll = useMemo(() => {
    const withInterested = (campaigns ?? []).find((c) => (c.interestedLeads ?? 0) > 0);
    return withInterested?.id || campaigns?.[0]?.id;
  }, [campaigns]);

  const handleViewAll = () => {
    if (campaignIdForViewAll) {
      navigate(`/app/campaigns/${campaignIdForViewAll}/leads?status=interested`);
    } else {
      navigate('/app/campaigns');
    }
  };

  return (
    <section className="cd-interested">
      <div className="cd-interested__header">
        <h2>Recent Interested Leads</h2>
        <button type="button" className="cd-interested__view-all" onClick={handleViewAll}>
          View All
          <span className="material-symbols-outlined">arrow_forward</span>
        </button>
      </div>

      <div className="cd-interested__table-wrap">
        <table className="cd-interested__table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Phone</th>
              <th>Outcome</th>
              <th>Campaign</th>
              <th>Time</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={5} className="cd-interested__empty">Loading…</td>
              </tr>
            )}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={5} className="cd-interested__empty">No interested leads yet.</td>
              </tr>
            )}
            {!loading &&
              rows.map((call) => {
                const campaign = campaigns.find((c) => c.id === call.campaignId);
                return (
                  <tr
                    key={call.sessionCallId}
                    className="cd-interested__row"
                    onClick={() =>
                      call.campaignId &&
                      navigate(`/app/campaigns/${call.campaignId}/leads?status=interested`)
                    }
                  >
                    <td>{call.leadName}</td>
                    <td className="cd-interested__mono">{call.leadPhone}</td>
                    <td>{outcomeLabel(call.outcome)}</td>
                    <td>{campaign?.name || campaign?.title || '—'}</td>
                    <td className="cd-interested__muted">
                      {call.createdAt
                        ? new Date(call.createdAt).toLocaleString('en-IN', {
                            day: 'numeric',
                            month: 'short',
                            hour: '2-digit',
                            minute: '2-digit',
                          })
                        : '—'}
                    </td>
                  </tr>
                );
              })}
          </tbody>
        </table>
      </div>
    </section>
  );
};

export default InterestedLeadsTable;
