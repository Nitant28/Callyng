import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import './RunningCampaigns.css';

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

const RunningCampaigns = ({ campaigns = [], loading, error }) => {
  const navigate = useNavigate();

  const running = useMemo(
    () => (campaigns ?? []).filter((c) => c.status === 'running' || c.status === 'pausing'),
    [campaigns],
  );

  return (
    <section className="cd-running">
      <div className="cd-running__header">
        <h2 className="cd-running__title">Running Campaigns</h2>
      </div>

      {error && <p className="cd-running__error">{error}</p>}

      {!loading && running.length === 0 && !error && (
        <div className="cd-running__empty">
          <span className="material-symbols-outlined cd-running__empty-icon">campaign</span>
          <p className="cd-running__empty-title">No Active Campaigns</p>
          <p className="cd-running__empty-desc">Create your first campaign to start calling.</p>
          <button
            type="button"
            className="cd-running__cta"
            onClick={() => navigate('/app/campaigns')}
          >
            Create Campaign
          </button>
        </div>
      )}

      {(loading || running.length > 0) && (
        <>
          <div className="cd-running__cols">
            <span>Campaign</span>
            <span>Status</span>
            <span>Progress</span>
            <span>Calls</span>
            <span>Interested</span>
            <span>Remaining</span>
          </div>
          <div className="cd-running__body">
            {loading && [1, 2, 3].map((i) => (
              <div key={i} className="cd-running__row cd-running__row--skel">
                <div className="ds-shimmer" style={{ height: 40, borderRadius: 12 }} />
              </div>
            ))}
            {!loading && running.map((c) => {
              const progress = c.totalLeads > 0
                ? Math.round(((c.completedLeads ?? 0) / c.totalLeads) * 100)
                : 0;
              const remaining = c.budgetCredits != null && c.creditsUsed != null
                ? Math.max(0, c.budgetCredits - c.creditsUsed)
                : null;

              return (
                <div
                  key={c.id}
                  className="cd-running__row"
                  role="button"
                  tabIndex={0}
                  onClick={() => navigate(`/app/campaigns/${c.id}`)}
                  onKeyDown={(e) => e.key === 'Enter' && navigate(`/app/campaigns/${c.id}`)}
                >
                  <div className="cd-running__name">
                    <span className="material-symbols-outlined cd-running__icon">campaign</span>
                    <span>{c.title}</span>
                  </div>
                  <span className={`cd-running__status cd-running__status--${c.status}`}>
                    {STATUS[c.status] ?? c.status}
                  </span>
                  <div className="cd-running__progress">
                    <div className="cd-running__progress-bar">
                      <div style={{ width: `${progress}%` }} />
                    </div>
                    <span>{progress}%</span>
                  </div>
                  <span className="cd-running__cell">{fmt(c.completedLeads ?? c.totalLeads)}</span>
                  <span className="cd-running__cell">{fmt(c.interestedLeads)}</span>
                  <span className="cd-running__cell">
                    {remaining != null ? `₹${fmt(remaining)}` : '—'}
                  </span>
                </div>
              );
            })}
          </div>
        </>
      )}
    </section>
  );
};

export default RunningCampaigns;
