import { Badge } from '../../../../components/enterprise';
import { formatCampaignDate, statusLabel, statusTone } from '../../../../utils/campaignHelpers';
import './CampaignCard.css';

const fmt = (n) => (n == null ? '—' : new Intl.NumberFormat('en-IN').format(n));
const fmtPct = (n) => (n == null ? '—' : `${n}%`);
const fmtCredits = (n) => (n == null ? '—' : `₹${fmt(n)}`);

const CampaignCard = ({ campaign, voiceAgentName, onOpen }) => {
  return (
    <article className="cmp-card">
      <div className="cmp-card__head">
        <div>
          <h3>{campaign.name}</h3>
          <Badge tone={statusTone(campaign.status)}>{statusLabel(campaign.status)}</Badge>
        </div>
        <span className="cmp-card__date">Created {formatCampaignDate(campaign.createdAt)}</span>
      </div>

      <p className="cmp-card__agent">
        <span className="material-symbols-outlined">smart_toy</span>
        {voiceAgentName || 'Voice Agent'}
      </p>

      <dl className="cmp-card__metrics">
        <div>
          <dt>Credits Used</dt>
          <dd>{fmtCredits(campaign.creditsUsed)}</dd>
        </div>
        <div>
          <dt>Total Leads</dt>
          <dd>{fmt(campaign.totalLeads)}</dd>
        </div>
        <div>
          <dt>Interested</dt>
          <dd>{fmt(campaign.interestedLeads)}</dd>
        </div>
        <div>
          <dt>Not Interested</dt>
          <dd>{fmt(campaign.notInterestedLeads)}</dd>
        </div>
        <div>
          <dt>Busy</dt>
          <dd>{fmt(campaign.busyLeads)}</dd>
        </div>
        <div>
          <dt>Conversion</dt>
          <dd>{fmtPct(campaign.conversionRate)}</dd>
        </div>
      </dl>

      <footer className="cmp-card__footer">
        <button type="button" className="cmp-card__open" onClick={onOpen}>
          Open Campaign
          <span className="material-symbols-outlined">arrow_forward</span>
        </button>
      </footer>
    </article>
  );
};

export default CampaignCard;
