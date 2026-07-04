import './BaseCard.css';

const BaseCard = ({ children, className = '', flat = false, as: Tag = 'div', ...props }) => (
  <Tag className={`ui-base-card ${flat ? 'ui-base-card--flat' : ''} ${className}`.trim()} {...props}>
    {children}
  </Tag>
);

export default BaseCard;
