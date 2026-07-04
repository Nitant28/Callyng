import { DATE_RANGE_OPTIONS } from './DashboardHeader';
import {
  buildDashboardKpis,
  formatLastSync,
  systemStatusMessage,
} from '../../../utils/dashboardKpis';
import { formatNumber as fmtNum } from './StatCard';
import './OperationsBanner.css';

const DateRangeDropdown = ({ value, onChange, options }) => {
  const selected = options.find((o) => o.value === value) ?? options[4];
  return (
    <select
      className="ops-banner__range"
      value={value}
      onChange={(e) => onChange?.(e.target.value)}
      aria-label="Date range"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
};

const OperationsBanner = ({
  clientName,
  credits,
  campaigns,
  error,
  lastUpdated,
  refreshLatencyMs,
  selectedRange,
  onRangeChange,
}) => {
  const name = clientName || 'Client';
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
  const kpis = buildDashboardKpis(credits, campaigns);
  const statusMsg = systemStatusMessage(error, campaigns);
  const hasError = error?.credits || error?.campaigns || error?.calls;
  const balance =
    credits?.balanceCredits != null ? `₹${fmtNum(credits.balanceCredits)}` : '—';

  return (
    <header className="ops-banner">
      <div className="ops-banner__main">
        <div>
          <h1 className="ops-banner__title">{greeting}, {name}</h1>
          <p className="ops-banner__status">{statusMsg}</p>
          <div className="ops-banner__chips">
            <span className="ops-banner__chip">
              <strong>{kpis.campaigns.running}</strong> running campaigns
            </span>
            <span className="ops-banner__chip">
              <strong>{kpis.concurrent.live}</strong> live calls
            </span>
            <span className="ops-banner__chip">
              <strong>{balance}</strong> credits left
            </span>
          </div>
        </div>
        <div className="ops-banner__ops">
          <DateRangeDropdown
            value={selectedRange}
            onChange={onRangeChange}
            options={DATE_RANGE_OPTIONS}
          />
          <div className={`ops-banner__health ${hasError ? 'ops-banner__health--warn' : ''}`}>
            <span className="ops-banner__health-dot" />
            {hasError ? 'Degraded' : 'All Systems Operational'}
          </div>
          <div className="ops-banner__meta">
            <span>Latency <strong>{refreshLatencyMs ?? '—'} ms</strong></span>
            <span>Last sync <strong>{formatLastSync(lastUpdated)}</strong></span>
          </div>
        </div>
      </div>
    </header>
  );
};

export default OperationsBanner;
