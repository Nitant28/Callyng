import { useMemo, useState, useEffect } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useCampaignWorkspace } from '../../../contexts/CampaignWorkspaceContext';
import StatsBar from '../../../components/client/StatsBar';
import clientApi from '../../../api/client';
import './AnalyticsTab.css';

const AnalyticsTab = () => {
  const { campaign, loading } = useCampaignWorkspace();
  const [calls, setCalls] = useState([]);
  const [callsLoading, setCallsLoading] = useState(false);

  useEffect(() => {
    if (!campaign?.id) return;
    setCallsLoading(true);
    clientApi.get('/api/calls', { params: { limit: 1000 } })
      .then(res => {
        const campaignCalls = (res.data?.calls || []).filter(c => c.campaign_id === campaign.id);
        setCalls(campaignCalls);
      })
      .catch(err => console.warn('Failed to load campaign calls', err))
      .finally(() => setCallsLoading(false));
  }, [campaign?.id]);

  const summary = useMemo(() => {
    if (!campaign) return [];
    return [
      { key: 'interested', label: 'Interested', value: campaign.interested_leads },
      { key: 'conversion', label: 'Conversion', value: campaign.conversion_rate, format: 'pct' },
      {
        key: 'credits',
        label: 'Credits Used',
        value: campaign.budget_used_credits || campaign.credits_used,
        format: 'credits',
      },
    ];
  }, [campaign]);

  const trendData = useMemo(() => {
    const now = new Date();
    const days = [];
    const buckets = {};
    for (let i = 6; i >= 0; i--) {
      const d = new Date(now);
      d.setDate(now.getDate() - i);
      const key = d.toLocaleDateString('en-IN', { weekday: 'short' });
      days.push(key);
      buckets[key] = { interested: 0, calls: 0 };
    }

    calls.forEach(c => {
      const d = new Date(c.started_at || c.created_at);
      const key = d.toLocaleDateString('en-IN', { weekday: 'short' });
      if (key in buckets) {
        buckets[key].calls++;
        if ((c.outcome || '').toLowerCase() === 'interested') {
          buckets[key].interested++;
        }
      }
    });

    return days.map(day => ({
      day,
      interested: buckets[day].interested,
      calls: buckets[day].calls,
    }));
  }, [calls]);

  const hourlyData = useMemo(() => {
    const buckets = {};
    for (let h = 9; h <= 20; h++) {
      buckets[`${h}:00`] = 0;
    }
    calls.forEach(c => {
      const d = new Date(c.started_at || c.created_at);
      const key = `${d.getHours()}:00`;
      if (key in buckets) {
        buckets[key]++;
      }
    });
    return Object.entries(buckets).map(([hour, calls]) => ({ hour, calls }));
  }, [calls]);

  if (!loading && !campaign) {
    return <p className="cw-analytics__empty">No analytics available.</p>;
  }

  return (
    <div className="cw-analytics">
      <StatsBar items={summary} loading={loading} />

      <div className="cw-analytics__grid">
        <section className="cw-analytics__chart">
          <h3>Interested Trend</h3>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="day" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Area type="monotone" dataKey="interested" stroke="#047857" fill="#6EE7B7" />
            </AreaChart>
          </ResponsiveContainer>
        </section>

        <section className="cw-analytics__chart">
          <h3>Call Volume</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="day" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="calls" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </section>

        <section className="cw-analytics__chart cw-analytics__chart--wide">
          <h3>Hourly Calls</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={hourlyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="hour" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="calls" fill="#10b981" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </section>
      </div>
    </div>
  );
};

export default AnalyticsTab;
