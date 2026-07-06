import './Button.css';

const Button = ({
  children,
  variant = 'primary',
  size = 'md',
  icon,
  loading,
  disabled,
  className = '',
  ...props
}) => (
  <button
    type="button"
    className={`ent-btn ent-btn--${variant} ent-btn--${size} ${className}`}
    disabled={disabled || loading}
    {...props}
  >
    {loading && <span className="material-symbols-outlined ent-btn__spin">progress_activity</span>}
    {icon && !loading && <span className="material-symbols-outlined">{icon}</span>}
    {children}
  </button>
);

export default Button;
