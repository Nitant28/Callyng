import { buildKpiMetrics, buildCampaignSummary } from './metrics.js';
import { buildGraphData } from './graph.js';
import { buildLiveActivity } from './activity.js';
import { buildCampaignRows } from './campaignSummary.js';

export const calculateDashboard = ({ campaigns = [], calls = [], balance = {}, options = {} } = {}) => {
  const metrics = buildKpiMetrics({ campaigns, calls, balance });
  const campaignSummary = buildCampaignSummary({ campaigns, calls });
  const campaignRows = buildCampaignRows(campaigns, calls);
  const graphData = buildGraphData(calls, options);
  const activityEvents = buildLiveActivity(calls, campaigns);

  return {
    metrics,
    campaignSummary,
    campaignRows,
    graphData,
    activityEvents,
    raw: { campaigns, calls, balance },
    generatedAt: new Date().toISOString(),
    options,
  };
};

export default calculateDashboard;
