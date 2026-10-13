import React from 'react';

const EmptyState = ({ icon = 'inbox', title = 'No Data Available', description, action }) => {
  return (
    <div style={{
      marginTop: '24px', 
      background: '#FFFFFF', 
      border: '1px dashed #CBD5E1',
      borderRadius: '12px', 
      padding: '48px', 
      textAlign: 'center',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center'
    }}>
      <div style={{
        width: '56px', 
        height: '56px', 
        borderRadius: '50%', 
        background: '#ECFDF5',
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'center',
        margin: '0 auto 16px', 
        color: '#047857',
      }}>
        <span className="material-symbols-outlined" style={{ fontSize: '28px' }}>{icon}</span>
      </div>
      <h3 style={{ fontFamily: 'Plus Jakarta Sans', fontSize: '18px', fontWeight: 700, color: '#0F172A', marginBottom: '8px', margin: 0 }}>
        {title}
      </h3>
      {description && (
        <p style={{ fontSize: '14px', color: '#64748B', maxWidth: '380px', margin: '8px auto 0', lineHeight: 1.5 }}>
          {description}
        </p>
      )}
      {action && <div style={{ marginTop: '16px' }}>{action}</div>}
    </div>
  );
};

export default EmptyState;
