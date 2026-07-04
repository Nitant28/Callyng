import React from 'react';

const ProgressBar = ({ value, max = 100, color = 'var(--blue)' }) => {
  const percentage = max > 0 ? (value / max) * 100 : 0;
  return (
    <div style={{ width: '100%', height: '4px', background: '#E2E8F0', borderRadius: '2px', overflow: 'hidden' }}>
      <div 
        style={{ 
          width: `${Math.min(Math.max(percentage, 0), 100)}%`, 
          height: '100%', 
          background: color, 
          borderRadius: '2px' 
        }} 
      />
    </div>
  );
};

export default ProgressBar;
