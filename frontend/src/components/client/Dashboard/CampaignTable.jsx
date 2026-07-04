import { useNavigate } from 'react-router-dom';
import { computeCampaignHealth } from '../../../utils/dashboardKpis';
import './CampaignTable.css';

const STATUS = {
  running: 'Running',
  paused: 'Paused',
  pausing: 'Paused',
  draft: 'Draft',
  completed: 'Completed',
  cancelled: 'Cancelled',
  failed: 'Failed',
};

const fmt = (n) => (n == null ? '0' : new Intl.NumberFormat('en-IN').format(n));
const fmtCredits = (n) => (n == null ? '—' : `₹${fmt(n)}`);

const conversionPct = (c) => {
  if (c.conversionRate != null) return c.conversionRate;
  return null;
};

const budgetPct = (c) => {
  if (!c.budgetCredits) return null;
  return Math.min(100, Math.round(((c.creditsUsed ?? 0) / c.budgetCredits) * 100));
};

const CampaignTable = ({ campaigns = [], loading, error }) => {
  const navigate = useNavigate();
  const rows = campaigns.slice(0, 5);

  return (
    <section className="cd-campaigns">
      <div className="cd-campaigns__header">
        <h2>Campaign Performance</h2>
      </div>
      {error && <p className="cd-campaigns__error">{error}</p>}
      <div className="cd-campaigns__cols">
        <span>Campaign</span>
        <span>Health</span>
        <span>Progress</span>
        <span>Calls</span>
        <span>Interested</span>
        <span>Conv.</span>
        <span>Budget</span>
        <span />
      </div>
      <div className="cd-campaigns__body">
        {loading && [1, 2, 3].map((i) => (
          <div key={i} className="cd-campaigns__row cd-campaigns__row--skel">
            <div className="ds-shimmer" style={{ height: 40, borderRadius: 12 }} />
            <div className="ds-shimmer" style={{ height: 24, width: 72, borderRadius: 999 }} />
            <div className="ds-shimmer" style={{ height: 14, width: 60 }} />
            <div className="ds-shimmer" style={{ height: 14, width: 40 }} />
            <div className="ds-shimmer" style={{ height: 14, width: 40 }} />
            <div className="ds-shimmer" style={{ height: 14, width: 50 }} />
            <div className="ds-shimmer" style={{ height: 14, width: 60 }} />
            <div />
          </div>
        ))}
        {!loading && campaigns.length === 0 && !error && (
          <div className="ds-empty">
            <span className="material-symbols-outlined ds-empty__icon">campaign</span>
            <p className="ds-empty__title">No campaigns running</p>
            <p className="ds-empty__desc">Launch your first campaign to begin monitoring AI performance.</p>
          </div>
        )}
        {!loading && rows.map((c) => {
          const health = computeCampaignHealth(c);
          const conv = conversionPct(c);
          const progress = c.totalLeads > 0
            ? Math.round(((c.completedLeads ?? 0) / c.totalLeads) * 100)
            : null;
          const budget = budgetPct(c);
          return (
            <div
              key={c.id}
              className="cd-campaigns__row"
              role="button"
              tabIndex={0}
              onClick={() => navigate(`/app/campaigns/${c.id}`)}
              onKeyDown={(e) => e.key === 'Enter' && navigate(`/app/campaigns/${c.id}`)}
            >
              <div className="cd-campaigns__identity">
                <div className="cd-campaigns__icon">
                  <span className="material-symbols-outlined">campaign</span>
                </div>
                <div>
                  <p className="cd-campaigns__name">{c.title}</p>
                  <span className={`cd-campaigns__status cd-campaigns__status--${c.status}`}>
                    {STATUS[c.status] ?? c.status}
                  </span>
                </div>
              </div>
              <span className={`cd-campaigns__health cd-campaigns__health--${health.tone}`}>
                {health.label}
              </span>
              <div className="cd-campaigns__progress">
                {progress != null ? (
                  <>
                    <div className="cd-campaigns__progress-bar">
                      <div style={{ width: `${progress}%` }} />
                    </div>
                    <span>{progress}%</span>
                  </>
                ) : (
                  <span>—</span>
                )}
              </div>
              <span className="cd-campaigns__cell">{fmt(c.totalLeads)}</span>
              <span className="cd-campaigns__cell">
                {c.interestedLeads != null ? fmt(c.interestedLeads) : '—'}
              </span>
              <div className="cd-campaigns__conv">
                {conv != null ? (
                  <>
                    <div className="cd-campaigns__conv-bar">
                      <div style={{ width: `${Math.min(100, conv)}%` }} />
                    </div>
                    <span>{conv.toFixed(1)}%</span>
                  </>
                ) : (
                  <span>—</span>
                )}
              </div>
              <div className="cd-campaigns__budget">
                <span>{fmtCredits(c.creditsUsed)}</span>
                {budget != null && (
                  <div className="cd-campaigns__budget-bar">
                    <div style={{ width: `${budget}%` }} />
                  </div>
                )}
              </div>
              <button
                type="button"
                className="cd-campaigns__action"
                aria-label="View campaign"
                onClick={(e) => {
                  e.stopPropagation();
                  navigate(`/app/campaigns/${c.id}`);
                }}
              >
                <span className="material-symbols-outlined">chevron_right</span>
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
};

export default CampaignTable;
