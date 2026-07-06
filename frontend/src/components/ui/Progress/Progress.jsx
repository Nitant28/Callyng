import './Progress.css';

const TONE_MAP = {
  blue: 'primary',
  primary: 'primary',
  green: 'success',
  success: 'success',
  orange: 'warning',
  warning: 'warning',
  red: 'danger',
  danger: 'danger',
  neutral: 'primary',
  purple: 'primary',
};

const Progress = ({ value = 0, tone = 'primary' }) => {
  const mapped = TONE_MAP[tone] || tone;
  const width = Math.min(100, Math.max(0, value));

  return (
    <div className="ui-progress" role="progressbar" aria-valuenow={width} aria-valuemin={0} aria-valuemax={100}>
      <div className={`ui-progress__fill ui-progress__fill--${mapped}`} style={{ width: `${width}%` }} />
    </div>
  );
};

export default Progress;
