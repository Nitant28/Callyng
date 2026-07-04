import './PageHeader.css';

const PageHeader = ({
  eyebrow,
  title,
  subtitle,
  bordered = false,
  children,
  className = '',
}) => (
  <header className={`page-header ${bordered ? 'page-header--bordered' : ''} ${className}`.trim()}>
    {eyebrow && <p className="page-header__eyebrow">{eyebrow}</p>}
    <div className="page-header__title-row">
      <div className="page-header__copy">
        <h1 className="page-header__title">{title}</h1>
        {subtitle && <p className="page-header__subtitle">{subtitle}</p>}
      </div>
      {children && <div className="page-header__actions">{children}</div>}
    </div>
  </header>
);

export default PageHeader;
