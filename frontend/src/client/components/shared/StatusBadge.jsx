import React from 'react';

const StatusBadge = ({ status, label }) => {
  const normalized = (status || '').toLowerCase().trim();
  
  let className = 'cl-badge cl-badge--failed';
  let displayLabel = label || status;
  
  if (normalized === 'live' || normalized === 'calling' || normalized === 'running') {
    className = 'cl-badge cl-badge--live';
    displayLabel = label || 'Live';
  } else if (normalized === 'interested' || normalized === 'connected' || normalized === 'success') {
    className = 'cl-badge cl-badge--interested';
    displayLabel = label || 'Interested';
  } else if (normalized === 'busy') {
    className = 'cl-badge cl-badge--busy';
    displayLabel = label || 'Busy';
  } else if (normalized === 'callback' || normalized === 'callback_scheduled' || normalized === 'callback requested') {
    className = 'cl-badge cl-badge--callback';
    displayLabel = label || 'Callback';
  } else if (normalized === 'rejected' || normalized === 'not_interested' || normalized === 'not interested') {
    className = 'cl-badge cl-badge--rejected';
    displayLabel = label || 'Not Interested';
  } else if (normalized === 'failed' || normalized === 'carrier_failed') {
    className = 'cl-badge cl-badge--failed';
    displayLabel = label || 'Failed';
  } else if (normalized === 'pending' || normalized === 'queued' || normalized === 'draft') {
    className = 'cl-badge cl-badge--failed'; // fallback to standard slate/grey badge style
    displayLabel = label || status;
  }
  
  return <span className={className}>{displayLabel}</span>;
};

export default StatusBadge;
