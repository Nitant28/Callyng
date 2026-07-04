import './Badge.css';

const TONES = {
  success: 'ent-badge--success',
  warning: 'ent-badge--warning',
  danger: 'ent-badge--danger',
  info: 'ent-badge--info',
  neutral: 'ent-badge--neutral',
};

const Badge = ({ children, tone = 'neutral' }) => (
  <span className={`ent-badge ${TONES[tone] || TONES.neutral}`}>{children}</span>
);

export default Badge;
