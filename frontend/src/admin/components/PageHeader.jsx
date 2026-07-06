import React from 'react';

export default function PageHeader({ title, description = null, action = null, className = '' }) {
  return (
    <header className={`admin-page-header ${className}`}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
        <div>
          <h1>{title}</h1>
          {description && <p>{description}</p>}
        </div>
        {action && <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>{action}</div>}
      </div>
    </header>
  );
}
