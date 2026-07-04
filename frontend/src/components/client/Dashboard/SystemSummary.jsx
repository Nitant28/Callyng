import { useMemo } from 'react';
import {
  buildExecutiveSummary,
  computeCallStats,
  formatDuration,
} from '../../../utils/dashboardKpis';
import './SystemSummary.css';

const sum = (campaigns, field) =>
  (campaigns ?? []).reduce((s, c) => s + (c[field] ?? 0), 0);

const SystemSummary = ({ campaigns = [], calls = [], credits, loading, refreshLatencyMs, lastUpdated }) => {
  const summary = useMemo(() => buildExecutiveSummary(calls, campaigns), [calls, campaigns]);
  const callStats = useMemo(() => computeCallStats(calls), [calls]);
  const failedLeads = sum(campaigns, 'failedLeads');
  const creditsUsed = sum(campaigns, 'creditsUsed');
  const calling = sum(campaigns, 'callingLeads');

  if (loading) {
    return (
      <aside className="sys-summary sys-summary--skel">
        <div className="ds-shimmer" style={{ height: 20, width: '50%', marginBottom: 12 }} />
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="ds-shimmer" style={{ height: 36, marginBottom: 8 }} />
        ))}
      </aside>
    );
  }

  return (
    <aside className="sys-summary">
      <h2 className="sys-summary__title">System Summary</h2>

      <div className="sys-summary__row">
        <span>Live calls</span>
        <strong>{calling}</strong>
      </div>
      <div className="sys-summary__row">
        <span>Failed leads</span>
        <strong>{failedLeads}</strong>
      </div>
      <div className="sys-summary__row">
        <span>Credits consumed</span>
        <strong>{creditsUsed.toLocaleString('en-IN')}</strong>
      </div>
      <div className="sys-summary__row">
        <span>Answer rate</span>
        <strong>
          {callStats.answerRate != null ? `${callStats.answerRate.toFixed(0)}%` : '—'}
        </strong>
      </div>
      <div className="sys-summary__row">
        <span>Avg duration</span>
        <strong>{formatDuration(callStats.avgDurationSec) ?? '—'}</strong>
      </div>

      <div className="sys-summary__divider" />

      <p className="sys-summary__section">{summary.label}</p>
      <div className="sys-summary__mini">
        <div><span>Attempted</span><strong>{summary.attempted}</strong></div>
        <div><span>Answered</span><strong>{summary.answered}</strong></div>
        <div><span>Interested</span><strong>{summary.interested}</strong></div>
        <div><span>Failed</span><strong>{summary.failed}</strong></div>
      </div>

      <div className="sys-summary__divider" />

      <div className="sys-summary__row">
        <span>API latency</span>
        <strong>{refreshLatencyMs != null ? `${refreshLatencyMs} ms` : '—'}</strong>
      </div>
      <div className="sys-summary__row">
        <span>Balance</span>
        <strong>
          {credits?.balanceCredits != null
            ? `₹${credits.balanceCredits.toLocaleString('en-IN')}`
            : '—'}
        </strong>
      </div>
    </aside>
  );
};

export default SystemSummary;
