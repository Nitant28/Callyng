import React from 'react';
import Badge from './Badge';

export default function CampaignCard({ campaign, clientName, onActionClick, onClick }) {
  const getStatusVariant = (status) => {
    switch (status) {
      case 'running': return 'success';
      case 'paused': return 'warning';
      case 'draft': return 'info';
      case 'completed': return 'success';
      case 'cancelled': return 'error';
      default: return 'neutral';
    }
  };

  const progress = campaign.total_leads > 0 
    ? Math.round((campaign.completed_leads / campaign.total_leads) * 100) 
    : 0;

  return (
    <div 
      className="arctic-card molten-card hover:translate-y-[-2px] transition-all duration-300 cursor-pointer p-6"
      onClick={onClick}
    >
      <div className="flex justify-between items-start mb-4">
        <div>
          <h4 className="font-headline-sm text-headline-sm text-on-background dark:text-molten-text">{campaign.name}</h4>
          <p className="font-caption text-caption text-on-surface-variant dark:text-molten-text-muted mt-1">
            Client: {clientName || 'Unknown'}
          </p>
        </div>
        <Badge variant={getStatusVariant(campaign.status)}>{campaign.status}</Badge>
      </div>

      <div className="space-y-4">
        <div>
          <div className="flex justify-between font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted mb-1">
            <span>Progress ({campaign.completed_leads} / {campaign.total_leads} leads)</span>
            <span>{progress}%</span>
          </div>
          <div className="w-full h-2 bg-surface-container-low dark:bg-[#2A345E] rounded-full overflow-hidden">
            <div 
              className="h-full bg-primary dark:bg-molten-primary transition-all duration-500" 
              style={{ width: `${progress}%` }}
            ></div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 border-t border-outline-variant/35 pt-4">
          <div>
            <p className="font-caption text-caption text-on-surface-variant dark:text-molten-text-muted">Budget</p>
            <p className="font-body-md text-body-md font-bold text-on-background dark:text-molten-text">₹{campaign.budget_credits?.toFixed(2)}</p>
          </div>
          <div>
            <p className="font-caption text-caption text-on-surface-variant dark:text-molten-text-muted">Spent</p>
            <p className="font-body-md text-body-md font-bold text-on-background dark:text-molten-text">₹{campaign.budget_used_credits?.toFixed(2)}</p>
          </div>
        </div>

        {onActionClick && (
          <div className="flex justify-end gap-2 border-t border-outline-variant/35 pt-4">
            {campaign.status === 'running' && (
              <button 
                onClick={(e) => { e.stopPropagation(); onActionClick('stop', campaign.id); }}
                className="px-3 py-1.5 text-xs font-semibold rounded bg-arctic-warning/20 dark:bg-molten-warning/20 text-arctic-warning dark:text-molten-warning hover:opacity-80"
              >
                Stop
              </button>
            )}
            {(campaign.status === 'draft' || campaign.status === 'paused') && (
              <button 
                onClick={(e) => { e.stopPropagation(); onActionClick('start', campaign.id); }}
                className="px-3 py-1.5 text-xs font-semibold rounded bg-primary/20 dark:bg-molten-primary/20 text-primary dark:text-molten-primary hover:opacity-80"
              >
                Start
              </button>
            )}
            {campaign.status !== 'completed' && campaign.status !== 'cancelled' && (
              <button 
                onClick={(e) => { e.stopPropagation(); onActionClick('cancel', campaign.id); }}
                className="px-3 py-1.5 text-xs font-semibold rounded bg-error-container dark:bg-molten-error/20 text-on-error-container dark:text-molten-error hover:opacity-80"
              >
                Cancel
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
