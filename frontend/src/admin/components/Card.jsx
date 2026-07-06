import React from 'react';

export default function Card({ children, className = '', title = null, headerAction = null }) {
  return (
    <div className={`admin-card ${className}`}>
      {(title || headerAction) && (
        <div className="admin-card__header">
          {title && <h3 className="admin-card__title">{title}</h3>}
          {headerAction && <div>{headerAction}</div>}
        </div>
      )}
      {children}
    </div>
  );
}
