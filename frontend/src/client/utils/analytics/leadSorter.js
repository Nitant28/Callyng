export const sortRecentCalls = (calls = []) => {
  return [...calls].sort((a, b) => {
    const aTime = new Date(a.started_at || a.created_at || a.timestamp).getTime() || 0;
    const bTime = new Date(b.started_at || b.created_at || b.timestamp).getTime() || 0;
    return bTime - aTime;
  });
};

export const sortCampaignsByActivity = (campaigns = [], calls = []) => {
  const counts = calls.reduce((acc, call) => {
    const campaignId = call.campaign_id || call.campaignId || 'unknown';
    acc[campaignId] = (acc[campaignId] || 0) + 1;
    return acc;
  }, {});

  return [...campaigns].sort((a, b) => (counts[b.id] || 0) - (counts[a.id] || 0));
};
