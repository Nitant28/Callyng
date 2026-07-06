import { Line, LineChart, ResponsiveContainer, YAxis } from 'recharts';
import './Sparkline.css';

const Sparkline = ({ data = [], color = '#2563eb', height = 36 }) => {
  const points = data.map((v, i) => ({ i, v }));
  const hasData = data.some((v) => v > 0);

  if (!hasData) {
    return <div className="ds-sparkline ds-sparkline--empty" style={{ height }} />;
  }

  return (
    <div className="ds-sparkline" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 4, right: 0, left: 0, bottom: 4 }}>
          <YAxis hide domain={['dataMin', 'dataMax']} />
          <Line
            type="monotone"
            dataKey="v"
            stroke={color}
            strokeWidth={2}
            dot={false}
            isAnimationActive
            animationDuration={700}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

export default Sparkline;
