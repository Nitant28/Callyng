import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';

const ChartTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload;
  return (
    <div className="cl-chart-tooltip">
      <div className="cl-chart-tooltip__label">{label}</div>
      <div className="cl-chart-tooltip__row">
        <span className="cl-chart-tooltip__dot cl-chart-tooltip__dot--green" />
        Interested: <strong>{point?.interested ?? 0}</strong>
      </div>
      <div className="cl-chart-tooltip__row">
        <span className="cl-chart-tooltip__dot cl-chart-tooltip__dot--blue" />
        Total calls: <strong>{point?.totalCalls ?? 0}</strong>
      </div>
    </div>
  );
};

const DashboardAnalytics = ({ chartData, callsCount = 0, period, onPeriodChange }) => {
  const hasChartPoints = chartData.some((d) => d.interested > 0 || d.totalCalls > 0);
  const hasCalls = callsCount > 0;

  return (
    <div className="cl-card cl-dashboard-chart">
      <div className="cl-dashboard-chart__header">
        <div>
          <h2 className="cl-card-title">Call Analytics</h2>
          <p className="cl-dashboard-chart__subtitle">
            {hasCalls ? `${callsCount} calls loaded` : 'Interested leads & call volume'}
          </p>
        </div>
        <select
          value={period}
          onChange={(e) => onPeriodChange(e.target.value)}
          className="cl-select cl-dashboard-chart__select"
          aria-label="Chart date range"
        >
          <option value="today">Today</option>
          <option value="yesterday">Yesterday</option>
          <option value="2d">Last 2 Days</option>
          <option value="3d">Last 3 Days</option>
          <option value="7d">Last Week</option>
          <option value="30d">Last Month</option>
          <option value="90d">Quarter</option>
          <option value="custom">Custom</option>
        </select>
      </div>

      <div className="cl-dashboard-chart__canvas">
        {!hasCalls ? (
          <div className="cl-dashboard-chart__empty">
            <span className="material-symbols-outlined">show_chart</span>
            <p>No call data yet</p>
            <span>Calls appear here once campaigns start dialing</span>
          </div>
        ) : !hasChartPoints ? (
          <div className="cl-dashboard-chart__empty">
            <span className="material-symbols-outlined">calendar_month</span>
            <p>No calls in this period</p>
            <span>Try a wider date range</span>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#EEF2F7" />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 11, fill: '#94A3B8' }}
                tickLine={false}
                axisLine={false}
                dy={8}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fontSize: 11, fill: '#94A3B8' }}
                tickLine={false}
                axisLine={false}
                allowDecimals={false}
                width={28}
              />
              <Tooltip content={<ChartTooltip />} />
              <Legend
                verticalAlign="top"
                height={28}
                iconType="circle"
                formatter={(value) => (
                  <span style={{ fontSize: 12, color: '#64748B' }}>{value}</span>
                )}
              />
              <Line
                type="monotone"
                dataKey="interested"
                name="Interested"
                stroke="#16A34A"
                strokeWidth={2.5}
                dot={{ r: 3, fill: '#16A34A' }}
                activeDot={{ r: 5 }}
              />
              <Line
                type="monotone"
                dataKey="totalCalls"
                name="Total calls"
                stroke="#047857"
                strokeWidth={2}
                dot={{ r: 2, fill: '#047857' }}
                activeDot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
};

export default DashboardAnalytics;
