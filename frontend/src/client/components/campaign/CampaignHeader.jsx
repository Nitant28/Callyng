import React from 'react';

export default function CampaignHeader({
  campaign,
  istStatus,
  isPausing,
  onToggleState,
  onReleaseStuck,
  isReleasingStuck,
  onCancelCampaign,
}) {
  return (
    <div className="cl-campaign-header animate-fade-in">
      <div className="cl-campaign-header__info">
        <h1 className="cl-campaign-header__name">{campaign?.name}</h1>
        <div className="cl-campaign-header__meta">
          <div className="cl-campaign-header__meta-item">
            <span className="material-symbols-outlined">tag</span>
            <span>Campaign ID: <span className="font-mono font-semibold">{campaign?.id}</span></span>
          </div>
          <div className="cl-campaign-header__meta-item">
            <span className="material-symbols-outlined">calendar_today</span>
            <span>Created: {campaign?.created_at ? new Date(campaign.created_at).toLocaleDateString() : 'N/A'}</span>
          </div>
          <div className="cl-campaign-header__meta-item">
            <span className="material-symbols-outlined">bolt</span>
            <span>Status: <span className={`cl-badge ${
              campaign?.status === 'running' ? 'cl-badge--running' :
              campaign?.status === 'paused' ? 'cl-badge--paused' :
              campaign?.status === 'pausing' ? 'cl-badge--paused' :
              campaign?.status === 'completed' ? 'cl-badge--completed' :
              campaign?.status === 'cancelled' ? 'cl-badge--cancelled' :
              'cl-badge--draft'
            }`}>{campaign?.status}</span></span>
          </div>
        </div>
      </div>

      <div className="cl-campaign-header__actions">
        {campaign?.status !== 'cancelled' && campaign?.status !== 'completed' && (
          <button
            onClick={onToggleState}
            className={`cl-btn ${campaign?.status === 'running' ? 'cl-btn--secondary' : 'cl-btn--primary'}`}
          >
            <span className="material-symbols-outlined">
              {campaign?.status === 'running' ? 'pause' : 'rocket_launch'}
            </span>
            {campaign?.status === 'running' ? 'Pause Campaign' : 'Start Campaign'}
          </button>
        )}
        {campaign?.calling_leads > 0 && ['running', 'pausing', 'paused'].includes(campaign?.status) && (
          <button
            onClick={onReleaseStuck}
            disabled={isReleasingStuck}
            className="cl-btn cl-btn--secondary"
          >
            <span className="material-symbols-outlined">lock_open</span>
            Release stuck leads
          </button>
        )}
        {campaign?.status === 'paused' && (
          <button
            onClick={onCancelCampaign}
            className="cl-btn cl-btn--danger-outline"
          >
            <span className="material-symbols-outlined">cancel</span>
            Cancel &amp; Refund
          </button>
        )}
      </div>
    </div>
  );
}
