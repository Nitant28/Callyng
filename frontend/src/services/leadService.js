import clientApi from '../api/client';

const mapLeadRow = (row, campaignName) => ({
  id: row.id,
  campaignId: row.campaign_id,
  campaignName: row.campaign_name || campaignName || 'Campaign',
  name: row.name,
  phone: row.phone,
  status: row.status,
  outcome: row.outcome || row.last_call_outcome,
  attempts: row.attempts ?? 0,
  maxAttempts: row.max_attempts ?? 3,
  leadType: row.lead_type,
  metadata: row.metadata || {},
  nextAttemptAt: row.next_attempt_at,
  scheduledCallbackAt: row.scheduled_callback_at,
  lastCalledAt: row.last_call_ended_at || row.updated_at,
  lastCallDurationSeconds: row.last_call_duration_seconds,
  createdAt: row.created_at,
  updatedAt: row.updated_at,
  sessionCallId: row.session_call_id || null,
  lastCallInProgress: row.last_call_in_progress ?? false,
});

const sortRows = (rows, sort, order) => {
  const dir = order === 'asc' ? 1 : -1;
  const fieldMap = {
    created_at: (r) => new Date(r.createdAt || 0).getTime(),
    updated_at: (r) => new Date(r.updatedAt || r.lastCalledAt || 0).getTime(),
    name: (r) => (r.name || '').toLowerCase(),
    status: (r) => (r.status || '').toLowerCase(),
    attempts: (r) => r.attempts ?? 0,
  };
  const getter = fieldMap[sort] || fieldMap.created_at;
  return [...rows].sort((a, b) => {
    const av = getter(a);
    const bv = getter(b);
    if (av < bv) return -1 * dir;
    if (av > bv) return 1 * dir;
    return 0;
  });
};

const paginate = (rows, page, limit) => {
  const total = rows.length;
  const pages = Math.max(1, Math.ceil(total / limit));
  const safePage = Math.min(Math.max(1, page), pages);
  const start = (safePage - 1) * limit;
  return {
    rows: rows.slice(start, start + limit),
    total,
    page: safePage,
    limit,
    pages,
  };
};

let globalApiAvailable = null;

const checkGlobalApi = async () => {
  if (globalApiAvailable != null) return globalApiAvailable;
  try {
    const res = await clientApi.get('/api/leads/stats', {
      validateStatus: () => true,
    });
    globalApiAvailable = res.status !== 404;
  } catch {
    globalApiAvailable = false;
  }
  return globalApiAvailable;
};

const listViaCampaigns = async ({
  page = 1,
  limit = 50,
  search,
  campaignId,
  status,
  sort = 'created_at',
  order = 'desc',
}) => {
  const campRes = await clientApi.get('/api/campaigns');
  let campaigns = campRes.data?.campaigns ?? [];
  if (campaignId) {
    campaigns = campaigns.filter((c) => String(c.id) === String(campaignId));
  }

  const batches = await Promise.all(
    campaigns.map(async (camp) => {
      try {
        const all = [];
        let offset = 0;
        const batchLimit = 200;
        let total = Infinity;
        while (offset < total) {
          const res = await clientApi.get(`/api/campaigns/${camp.id}/leads`, {
            params: {
              limit: batchLimit,
              offset,
              status: status || undefined,
              search: search || undefined,
            },
          });
          const chunk = res.data?.leads ?? [];
          total = res.data?.total_count ?? chunk.length;
          all.push(...chunk.map((row) => mapLeadRow(row, camp.name)));
          if (chunk.length < batchLimit) break;
          offset += batchLimit;
        }
        return all;
      } catch {
        return [];
      }
    }),
  );

  const merged = sortRows(batches.flat(), sort, order);
  return paginate(merged, page, limit);
};

const statsViaCampaigns = async ({ campaignId } = {}) => {
  const campRes = await clientApi.get('/api/campaigns');
  let campaigns = campRes.data?.campaigns ?? [];
  if (campaignId) {
    campaigns = campaigns.filter((c) => String(c.id) === String(campaignId));
  }

  const stats = {
    uploaded: 0,
    pending: 0,
    callback: 0,
    completed: 0,
    failed: 0,
    calling: 0,
    interested: 0,
  };

  campaigns.forEach((c) => {
    stats.uploaded += c.total_leads ?? 0;
    stats.pending += c.pending_leads ?? 0;
    stats.callback += c.callback_leads ?? 0;
    stats.completed += c.completed_leads ?? 0;
    stats.failed += c.failed_leads ?? 0;
    stats.calling += c.calling_leads ?? 0;
    if (c.interested_leads != null) {
      stats.interested += c.interested_leads;
    }
  });

  return stats;
};

export const leadService = {
  async list({
    page = 1,
    limit = 50,
    search,
    campaignId,
    status,
    sort = 'created_at',
    order = 'desc',
  } = {}) {
    const hasGlobal = await checkGlobalApi();
    if (!hasGlobal) {
      return listViaCampaigns({ page, limit, search, campaignId, status, sort, order });
    }

    try {
      const res = await clientApi.get('/api/leads', {
        params: {
          page,
          limit,
          search: search || undefined,
          campaign_id: campaignId || undefined,
          status: status || undefined,
          sort,
          order,
        },
      });
      const data = res.data || {};
      return {
        rows: (data.rows || []).map((row) => mapLeadRow(row)),
        total: data.total ?? 0,
        page: data.page ?? page,
        limit: data.limit ?? limit,
        pages: data.pages ?? 1,
      };
    } catch (err) {
      if (err.response?.status === 404) {
        globalApiAvailable = false;
        return listViaCampaigns({ page, limit, search, campaignId, status, sort, order });
      }
      throw err;
    }
  },

  async listAll(params = {}) {
    const all = [];
    let page = 1;
    let pages;
    const limit = 200;
    do {
      const batch = await this.list({ ...params, page, limit });
      all.push(...batch.rows);
      pages = batch.pages || 0;
      page += 1;
    } while (page <= pages);
    return all;
  },

  async stats({ campaignId } = {}) {
    const hasGlobal = await checkGlobalApi();
    if (!hasGlobal) {
      return statsViaCampaigns({ campaignId });
    }

    try {
      const res = await clientApi.get('/api/leads/stats', {
        params: { campaign_id: campaignId || undefined },
      });
      return res.data?.stats ?? {};
    } catch (err) {
      if (err.response?.status === 404) {
        globalApiAvailable = false;
        return statsViaCampaigns({ campaignId });
      }
      throw err;
    }
  },

  invalidateApiCache() {
    globalApiAvailable = null;
  },

  async get(campaignId, leadId) {
    const res = await clientApi.get(`/api/campaigns/${campaignId}/leads/${leadId}`);
    return mapLeadRow(res.data?.lead || {});
  },

  async update(campaignId, leadId, body) {
    const res = await clientApi.patch(`/api/campaigns/${campaignId}/leads/${leadId}`, body);
    return mapLeadRow(res.data?.lead || {});
  },

  async delete(campaignId, leadId) {
    await clientApi.delete(`/api/campaigns/${campaignId}/leads/${leadId}`);
    leadService.invalidateApiCache();
  },

  async add(campaignId, body) {
    const res = await clientApi.post(`/api/campaigns/${campaignId}/leads`, body);
    leadService.invalidateApiCache();
    return mapLeadRow(res.data?.lead || {});
  },

  async importCsv(campaignId, file, onUploadProgress) {
    const form = new FormData();
    form.append('file', file);
    const res = await clientApi.post(`/api/campaigns/${campaignId}/leads/upload`, form, {
      onUploadProgress,
    });
    leadService.invalidateApiCache();
    return res.data;
  },

  async downloadTemplate(campaignId) {
    const res = await clientApi.get(`/api/campaigns/${campaignId}/leads/template`, {
      responseType: 'blob',
    });
    return res.data;
  },

  triggerCsvDownload(filename, csvText) {
    const blob = new Blob([csvText], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  },
};

export default leadService;
