import React from 'react';

const PageHeader = ({ title, subtitle, actions }) => {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
      <div>
        <h1 className="cl-page-title">{title}</h1>
        {subtitle && <p className="cl-body" style={{ color: '#64748B', marginTop: '8px' }}>{subtitle}</p>}
      </div>
      {actions && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {actions}
        </div>
      )}
    </div>
  );
};

export default PageHeader;
