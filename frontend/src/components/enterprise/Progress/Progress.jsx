import './Progress.css';

const Progress = ({ value = 0, tone = 'primary' }) => (
  <div className="ent-progress">
    <div
      className={`ent-progress__fill ent-progress__fill--${tone}`}
      style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
    />
  </div>
);

export default Progress;
