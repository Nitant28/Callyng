import React from 'react';

export const Card = ({ children, className = '', ...props }) => {
  return (
    <div 
      className={`bg-arctic-surface dark:bg-molten-surface p-5 rounded-lg border border-outline-variant/50 dark:border-[#2A345E] shadow-[0_4px_20px_rgba(22,71,232,0.05)] dark:shadow-none transition-all duration-300 ${className}`}
      {...props}
    >
      {children}
    </div>
  );
};
