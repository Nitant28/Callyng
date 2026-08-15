import { useCallback, useEffect, useState } from 'react';
import clientApi from '../../../api/client';
import { useCampaignWorkspace } from '../../../contexts/CampaignWorkspaceContext';
import CallTable from '../../../components/client/CallTable';
import TranscriptDrawer from '../../../components/client/TranscriptDrawer';
import './CallsTab.css';

const LIMIT = 25;

const CallsTab = () => {
  const { campaignId, campaign } = useCampaignWorkspace();
  const [calls, setCalls] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const loadCalls = useCallback(async () => {
    if (!campaignId) return;
    setLoading(true);
    try {
      const res = await clientApi.get(`/api/campaigns/${campaignId}/calls`, {
        params: { limit: LIMIT, offset, search: search || undefined },
      });
      const rows = (res.data?.calls || []).map((row) => ({
        sessionCallId: row.session_call_id,
        leadName: row.name || 'Unknown',
        leadPhone: row.phone || '',
        outcome: row.outcome,
        durationSeconds: row.duration_seconds ?? 0,
        createdAt: row.created_at,
        inProgress: row.in_progress === true,
        creditsCharged: row.credits_charged ?? null,
      }));
      setCalls(rows);
      setTotal(res.data?.total_count ?? rows.length);
    } catch {
      setCalls([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [campaignId, offset, search]);

  useEffect(() => {
    const t = setTimeout(() => loadCalls(), 0);
    return () => clearTimeout(t);
  }, [loadCalls]);

  useEffect(() => {
    setOffset(0);
  }, [search]);

  return (
    <div className="cw-calls">
      <div className="cw-calls__toolbar">
        <label className="cw-calls__search">
          <span className="material-symbols-outlined">search</span>
          <input
            type="search"
            placeholder="Search calls…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <button type="button" className="cw-calls__refresh" onClick={loadCalls}>
          <span className="material-symbols-outlined">refresh</span>
          Refresh
        </button>
      </div>

      <CallTable
        calls={calls}
        loading={loading}
        onOpen={(call) => {
          setSelected(call);
          setDrawerOpen(true);
        }}
        onTranscript={(call) => {
          setSelected(call);
          setDrawerOpen(true);
        }}
      />

      {total > LIMIT && (
        <footer className="cw-calls__pagination">
          <span>
            {offset + 1}–{Math.min(offset + LIMIT, total)} of {total}
          </span>
          <div>
            <button type="button" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - LIMIT))}>
              Previous
            </button>
            <button
              type="button"
              disabled={offset + LIMIT >= total}
              onClick={() => setOffset((o) => o + LIMIT)}
            >
              Next
            </button>
          </div>
        </footer>
      )}

      <TranscriptDrawer
        open={drawerOpen}
        call={selected}
        campaignName={campaign?.name}
        onClose={() => setDrawerOpen(false)}
      />
    </div>
  );
};

export default CallsTab;
