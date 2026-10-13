import { useMemo, useState } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { bucketCallsByRange, CHART_RANGES } from '../../../utils/dateRangeHelpers';
import './AnalyticsChart.css';

const ChartTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="cd-chart__tooltip">
      <p className="cd-chart__tooltip-label">{label}</p>
      <p className="cd-chart__tooltip-value">Calls: {payload[0]?.value ?? 0}</p>
    </div>
  );
};

const AnalyticsChart = ({ calls = [], loading }) => {
  const [range, setRange] = useState('7d');

  const { chartData, hasData } = useMemo(() => {
    const buckets = bucketCallsByRange(calls, range);
    return {
      chartData: buckets.map((p) => ({ label: p.label, calls: p.count })),
      hasData: buckets.length > 0,
    };
  }, [calls, range]);

  return (
    <section className="cd-chart">
      <div className="cd-chart__header">
        <h2 className="cd-chart__title">Calls</h2>
        <select
          className="cd-chart__select"
          value={range}
          onChange={(e) => setRange(e.target.value)}
          aria-label="Chart date range"
        >
          {CHART_RANGES.map((r) => (
            <option key={r.id} value={r.id}>{r.label}</option>
          ))}
        </select>
      </div>

      <div className="cd-chart__canvas">
        {loading && <div className="cd-chart__empty ds-shimmer" />}

        {!loading && !hasData && (
          <div className="ds-empty cd-chart__empty">
            <p className="ds-empty__title">No calls in this period</p>
          </div>
        )}

        {!loading && hasData && (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 6" vertical={false} />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 12, fill: '#64748b' }}
                axisLine={false}
                tickLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fontSize: 12, fill: '#64748b' }}
                axisLine={false}
                tickLine={false}
                allowDecimals={false}
                width={32}
              />
              <Tooltip content={<ChartTooltip />} />
              <Line
                type="monotone"
                dataKey="calls"
                name="Calls"
                stroke="#047857"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
};

export default AnalyticsChart;
