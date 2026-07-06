import React from 'react';

export default function TableToolbar({ children, className = '' }) {
  return (
    <div className={`admin-toolbar ${className}`}>
      {children}
    </div>
  );
}
