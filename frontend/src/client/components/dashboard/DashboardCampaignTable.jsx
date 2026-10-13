const DashboardCampaignTable = ({ campaigns, onCampaignClick }) => (
  <div className="cl-card">
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
      <h2 className="cl-card-title">Campaign Summary</h2>
      <span className="cl-caption" style={{ color: '#94A3B8', fontWeight: 600 }}>From live campaign + call data</span>
    </div>

    <div className="cl-table-container">
      <table className="cl-table">
        <thead>
          <tr>
            <th>Campaign</th>
            <th>Status</th>
            <th style={{ textAlign: 'right' }}>Interested</th>
            <th style={{ textAlign: 'right' }}>Answered</th>
            <th style={{ textAlign: 'right' }}>Conversion</th>
            <th style={{ textAlign: 'right' }}>Credits Used</th>
            <th style={{ textAlign: 'right' }}>Updated</th>
          </tr>
        </thead>
        <tbody>
          {campaigns.length === 0 ? (
            <tr>
              <td colSpan="7" style={{ textAlign: 'center', color: '#94A3B8' }}>
                No campaigns found.
              </td>
            </tr>
          ) : (
            campaigns.slice(0, 8).map((camp) => {
              const lastUpdatedStr = camp.updatedAt
                ? new Date(camp.updatedAt).toLocaleDateString('en-IN', {
                    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                  })
                : '—';
              const rowId = camp.campaignId || camp.id;

              return (
                <tr
                  key={rowId}
                  className="cl-table"
                  onClick={() => onCampaignClick?.(camp)}
                  style={{ cursor: onCampaignClick ? 'pointer' : 'default' }}
                >
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <div style={{
                        width: '32px', height: '32px', borderRadius: '8px', background: '#F8FAFC',
                        display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748B',
                      }}>
                        <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>
                          {camp.campaignName?.toLowerCase().includes('real estate') ? 'home' : 'business_center'}
                        </span>
                      </div>
                      <div>
                        <div style={{ fontWeight: 600, color: '#0F172A', fontSize: '13px' }}>{camp.campaignName}</div>
                        <div style={{ fontSize: '11px', color: '#64748B' }}>
                          {camp.createdAt
                            ? new Date(camp.createdAt).toLocaleDateString('en-IN', { month: 'short', day: 'numeric', year: 'numeric' })
                            : '—'}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <span style={{
                      fontWeight: 700,
                      color: camp.status === 'running' ? '#16A34A' : camp.callingLeads > 0 ? '#047857' : '#64748B',
                    }}>
                      {camp.status === 'running' ? 'Running' : camp.status || '—'}
                      {camp.callingLeads > 0 ? ` (${camp.callingLeads} live)` : ''}
                    </span>
                  </td>
                  <td style={{ textAlign: 'right', color: '#16A34A', fontWeight: 600 }}>
                    {(camp.interested || 0).toLocaleString()}
                  </td>
                  <td style={{ textAlign: 'right', color: '#7C3AED', fontWeight: 600 }}>
                    {(camp.answered || 0).toLocaleString()}
                  </td>
                  <td style={{ textAlign: 'right', fontWeight: 500 }}>
                    {typeof camp.conversion === 'number' ? `${camp.conversion}%` : '—'}
                  </td>
                  <td style={{ textAlign: 'right', fontWeight: 500 }}>
                    {(camp.creditsUsed || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                  </td>
                  <td style={{ textAlign: 'right', fontSize: '12px', color: '#64748B' }}>
                    {lastUpdatedStr}
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  </div>
);

export default DashboardCampaignTable;
