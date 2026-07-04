import { Badge } from '../../../../components/enterprise';
import { statusLabel, statusTone } from '../../../../utils/campaignHelpers';
import CampaignSkeleton from './CampaignSkeleton';
import CampaignEmpty from './CampaignEmpty';
import './CampaignListTable.css';

const fmt = (n) => (n == null ? '—' : new Intl.NumberFormat('en-IN').format(n));
const fmtBudget = (n) => (n == null ? '—' : `₹${fmt(n)}`);
const fmtPct = (n) => (n == null ? '—' : `${Number(n).toFixed(1)}%`);
const fmtDate = (iso) => {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
};

const CampaignListTable = ({
  campaigns,
  loading,
  selected,
  onToggleSelect,
  onOpen,
  onCreate,
  activeTab,
}) => {
  if (loading) {
    return (
      <div className="cmp-table-wrap">
        {Array.from({ length: 5 }).map((_, i) => (
          <CampaignSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (!campaigns.length) {
    return <CampaignEmpty onCreate={onCreate} activeTab={activeTab} />;
  }

  return (
    <div className="cmp-table-wrap">
      <div className="cmp-table-scroll">
        <table className="cmp-table">
          <thead>
            <tr>
              <th className="cmp-table__check" aria-label="Select" />
              <th>Campaign</th>
              <th>Status</th>
              <th>Budget</th>
              <th>Leads</th>
              <th>Calling</th>
              <th>Interested</th>
              <th>Conversion</th>
              <th>Updated</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {campaigns.map((campaign) => (
              <tr
                key={campaign.id}
                className={`cmp-table__row ${selected.has(campaign.id) ? 'cmp-table__row--selected' : ''}`}
                onClick={() => onOpen(campaign)}
              >
                <td className="cmp-table__check" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={selected.has(campaign.id)}
                    onChange={() => onToggleSelect(campaign.id)}
                    aria-label={`Select ${campaign.name}`}
                  />
                </td>
                <td>
                  <div className="cmp-table__name">{campaign.name}</div>
                </td>
                <td>
                  <Badge tone={statusTone(campaign.status)}>{statusLabel(campaign.status)}</Badge>
                </td>
                <td className="cmp-table__num">{fmtBudget(campaign.budgetCredits)}</td>
                <td className="cmp-table__num">{fmt(campaign.totalLeads)}</td>
                <td className="cmp-table__num">{fmt(campaign.callingLeads)}</td>
                <td className="cmp-table__num">{fmt(campaign.interestedLeads)}</td>
                <td className="cmp-table__num">{fmtPct(campaign.conversionRate)}</td>
                <td className="cmp-table__muted">{fmtDate(campaign.createdAt)}</td>
                <td className="cmp-table__action" onClick={(e) => e.stopPropagation()}>
                  <button type="button" onClick={() => onOpen(campaign)} aria-label="Open campaign">
                    <span className="material-symbols-outlined">chevron_right</span>
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default CampaignListTable;
