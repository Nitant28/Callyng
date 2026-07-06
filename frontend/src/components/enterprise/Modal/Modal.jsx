import { useEffect } from 'react';
import './Modal.css';

const Modal = ({
  open,
  onClose,
  title,
  subtitle,
  icon,
  children,
  footer,
  width = 560,
}) => {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="ent-modal__backdrop" onClick={onClose} role="presentation">
      <div
        className="ent-modal"
        style={{ maxWidth: width }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header className="ent-modal__header">
          <div className="ent-modal__title-wrap">
            {icon && (
              <div className="ent-modal__icon" aria-hidden>
                <span className="material-symbols-outlined">{icon}</span>
              </div>
            )}
            <div className="ent-modal__title-copy">
              <h2>{title}</h2>
              {subtitle && <p className="ent-modal__subtitle">{subtitle}</p>}
            </div>
          </div>
          <button type="button" className="ent-modal__close" onClick={onClose} aria-label="Close">
            <span className="material-symbols-outlined">close</span>
          </button>
        </header>
        <div className="ent-modal__body">{children}</div>
        {footer && <footer className="ent-modal__footer">{footer}</footer>}
      </div>
    </div>
  );
};

export default Modal;
