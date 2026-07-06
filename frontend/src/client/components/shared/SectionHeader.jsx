import React from 'react';

const SectionHeader = ({ title, actions, style }) => {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', ...style }}>
      <h2 className="cl-card-title" style={{ fontSize: '14px', fontWeight: 700, color: '#0F172A' }}>{title}</h2>
      {actions && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {actions}
        </div>
      )}
    </div>
  );
};

export default SectionHeader;
