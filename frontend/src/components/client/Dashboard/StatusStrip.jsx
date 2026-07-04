import { formatLastSync } from '../../../utils/dashboardKpis';
import './StatusStrip.css';

const StatusStrip = ({ error, refreshLatencyMs, lastUpdated }) => {
  const hasError = error?.credits || error?.campaigns || error?.calls;
  const items = [
    { label: 'System', value: hasError ? 'Degraded' : 'Operational', ok: !hasError },
    { label: 'Latency', value: refreshLatencyMs != null ? `${refreshLatencyMs} ms` : '—', ok: refreshLatencyMs != null && refreshLatencyMs < 500 },
    { label: 'API', value: hasError ? 'Error' : 'Connected', ok: !hasError },
    { label: 'Voice', value: hasError ? 'Check' : 'Connected', ok: !hasError },
  ];

  return (
    <div className="status-strip">
      {items.map((item) => (
        <div key={item.label} className="status-strip__item">
          <span className="status-strip__label">{item.label}</span>
          <span className={`status-strip__value ${item.ok ? 'status-strip__value--ok' : 'status-strip__value--warn'}`}>
            <span className="status-strip__dot" />
            {item.value}
          </span>
        </div>
      ))}
      <div className="status-strip__sync">
        Synced {formatLastSync(lastUpdated)}
      </div>
    </div>
  );
};

export default StatusStrip;
