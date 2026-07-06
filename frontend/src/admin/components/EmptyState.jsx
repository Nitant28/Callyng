import React from 'react';

export default function EmptyState({ 
  title = 'No records found', 
  message = 'Get started by creating a new entry.', 
  icon = 'folder_open', 
  action = null 
}) {
  return (
    <div className="flex flex-col items-center justify-center p-12 text-center bg-surface-container-lowest dark:bg-molten-surface border border-outline-variant/35 rounded-lg">
      <span className="material-symbols-outlined text-4xl text-on-surface-variant dark:text-molten-text-muted mb-4">
        {icon}
      </span>
      <h3 className="font-headline-sm text-headline-sm text-on-background dark:text-molten-text mb-2">
        {title}
      </h3>
      <p className="font-body-md text-body-md text-on-surface-variant dark:text-molten-text-muted max-w-sm mb-6">
        {message}
      </p>
      {action && <div>{action}</div>}
    </div>
  );
}
