import { buildCampaignSummary } from './metrics.js';

export const buildCampaignRows = (campaigns = [], calls = []) =>
  buildCampaignSummary({ campaigns, calls });
