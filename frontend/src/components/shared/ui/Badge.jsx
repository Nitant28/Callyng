import React from 'react';

export const Badge = ({ status, className = '' }) => {
  let badgeClasses = 'bg-arctic-text-muted/15 text-arctic-text-muted';
  let label = status;

  switch (status?.toLowerCase()) {
    case 'running':
      badgeClasses = 'bg-primary/15 text-primary dark:bg-molten-primary/15 dark:text-molten-primary';
      label = (
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 bg-primary dark:bg-molten-primary rounded-full animate-pulse"></span>
          Running
        </span>
      );
      break;
    case 'paused':
      badgeClasses = 'bg-arctic-warning/15 text-arctic-warning';
      break;
    case 'completed':
      badgeClasses = 'bg-secondary/15 text-secondary dark:bg-molten-success/15 dark:text-molten-success';
      break;
    case 'failed':
    case 'error':
      badgeClasses = 'bg-error/15 text-error dark:bg-molten-error/15 dark:text-molten-error';
      break;
    default:
      break;
  }

  return (
    <span className={`px-3 py-1 rounded-full text-label-sm font-bold uppercase ${badgeClasses} ${className}`}>
      {label}
    </span>
  );
};
