import React from 'react';

export default function Badge({ children, variant = 'info', className = '' }) {
  const baseClasses = 'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold border';
  
  const variants = {
    success: 'bg-secondary-container/20 text-secondary border-secondary/20 dark:text-molten-success dark:border-molten-success/20',
    error: 'bg-error-container/20 text-error border-error/20 dark:text-molten-error dark:border-molten-error/20',
    warning: 'bg-yellow-500/10 text-yellow-600 border-yellow-500/20 dark:text-molten-success dark:border-molten-success/20',
    info: 'bg-primary-container/10 text-primary border-primary/20 dark:text-molten-primary dark:border-molten-primary/20',
    neutral: 'bg-surface-container-high text-on-surface-variant border-outline-variant dark:text-molten-text-muted dark:border-outline/20'
  };

  return (
    <span className={`${baseClasses} ${variants[variant]} ${className}`}>
      {children}
    </span>
  );
}
