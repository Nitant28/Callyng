import { useMemo, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useToast } from '../../contexts/ToastContext';
import clientApi from '../../api/client';
import LoaderOverlay from '../components/LoaderOverlay';
import CallTranscriptDrawer from '../components/CallTranscriptDrawer';
import { useDashboardData } from '../../contexts/DashboardDataContext';
import { calculateDashboard } from '../utils/analytics';

import DashboardHeader from '../components/dashboard/DashboardHeader';
import DashboardKPIs from '../components/dashboard/DashboardKPIs';
import DashboardAnalytics from '../components/dashboard/DashboardAnalytics';
import DashboardActivity from '../components/dashboard/DashboardActivity';
import DashboardCampaignTable from '../components/dashboard/DashboardCampaignTable';
import DashboardScopeTabs from '../components/dashboard/DashboardScopeTabs';
import CreditsWarningBanner from '../components/dashboard/CreditsWarningBanner';
import DashboardInterestedLeads from '../components/dashboard/DashboardInterestedLeads';
import MetricCard from '../components/shared/MetricCard';

const getIstStatus = () => {
  const now = new Date();
  const ist = new Date(now.getTime() + now.getTimezoneOffset() * 60000 + 5.5 * 3600000);
  const h = ist.getHours();
  const m = ist.getMinutes();
  const ampm = h >= 12 ? 'PM' : 'AM';
  const dh = h % 12 || 12;
  const dm = m < 10 ? '0' + m : m;
  return {
    isInside: h >= 9 && h < 21,
    formatted: `${dh}:${dm} ${ampm} IST`,
  };
};

const Dashboard = () => {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { loading, refreshing, balance, campaigns, calls, totalCalls, refresh } = useDashboardData();
  const clientName = localStorage.getItem('client_name') || balance?.client_name || 'Client';

  const [istStatus, setIstStatus] = useState(getIstStatus());
  const [period, setPeriod] = useState('7d');
  const [customStart, setCustomStart] = useState('');
  const [customEnd, setCustomEnd] = useState('');
  const [confirmStart, setConfirmStart] = useState(null);
  const [scopeTab, setScopeTab] = useState('overall');
  const [drawerCall, setDrawerCall] = useState(null);

  const runningCampaigns = useMemo(
    () => (campaigns || []).filter((c) => c.status === 'running'),
    [campaigns],
  );

  const scopeTabs = useMemo(
    () => [
      { id: 'overall', label: 'Overall' },
      ...runningCampaigns.map((c) => ({
        id: String(c.id),
        label: c.name || 'Campaign',
        live: true,
      })),
    ],
    [runningCampaigns],
  );

  useEffect(() => {
    if (scopeTab === 'overall') return;
    if (!runningCampaigns.some((c) => String(c.id) === String(scopeTab))) {
      setScopeTab('overall');
    }
  }, [runningCampaigns, scopeTab]);

  const scopedCampaigns = useMemo(() => {
    if (scopeTab === 'overall') return campaigns || [];
    return (campaigns || []).filter((c) => String(c.id) === String(scopeTab));
  }, [campaigns, scopeTab]);

  const scopedCalls = useMemo(() => {
    if (scopeTab === 'overall') return calls || [];
    return (calls || []).filter((c) => String(c.campaign_id) === String(scopeTab));
  }, [calls, scopeTab]);

  const activeCampaign = scopedCampaigns[0] || null;
  const isCampaignScope = scopeTab !== 'overall';

  const { graphData, activityEvents, metrics, campaignSummary } = calculateDashboard({
    balance,
    campaigns: scopedCampaigns,
    calls: scopedCalls,
    options: { period, customStart, customEnd },
  });

  useEffect(() => {
    const id = setInterval(() => setIstStatus(getIstStatus()), 30000);
    return () => clearInterval(id);
  }, []);

  const handleCampaignClick = (camp) => {
    const campaignId = camp.campaignId || camp.id;
    if (!campaignId) return;
    navigate(`/app/campaigns/${campaignId}`);
  };

  const handleConfirmStart = async () => {
    if (!confirmStart) return;
    try {
      await clientApi.patch(`/api/campaigns/${confirmStart.id}/start`);
      showToast('Campaign started.', 'success');
      setConfirmStart(null);
      refresh();
    } catch (err) {
      showToast(err.customErrorMessage || 'Failed to start campaign', 'error');
    }
  };

  const isPausing = campaigns.some(
    (c) => c.status === 'pausing' || (c.status === 'paused' && (c.calling_leads || 0) > 0),
  );

  const totalLeads = Number(activeCampaign?.total_leads || 0);
  const completedLeads = Number(activeCampaign?.completed_leads || 0);
  const campaignProgress = totalLeads > 0 ? Math.round((completedLeads / totalLeads) * 1000) / 10 : 0;
  const conversion = Number(
    activeCampaign?.conversion_rate != null
      ? activeCampaign.conversion_rate
      : campaignSummary[0]?.conversion || 0,
  );

  return (
    <div className="cl-page-container">
      <LoaderOverlay isVisible={isPausing} message="Finishing ongoing leads..." />
      <LoaderOverlay isVisible={loading} message="Loading metrics..." />

      <CreditsWarningBanner
        remainingCredits={metrics.remainingCredits}
        onRecharge={() => showToast('Contact your account manager to recharge credits.', 'info')}
      />

      <DashboardScopeTabs tabs={scopeTabs} activeId={scopeTab} onChange={setScopeTab} />

      <DashboardHeader
        clientName={clientName}
        period={period}
        onPeriodChange={setPeriod}
        customStart={customStart}
        customEnd={customEnd}
        onCustomStartChange={setCustomStart}
        onCustomEndChange={setCustomEnd}
        refreshing={refreshing}
        onRefresh={refresh}
      />

      {!loading && (
        <>
          {isCampaignScope ? (
            <div className="cl-dashboard-kpis cl-mb-section">
              <MetricCard
                label="Total Calls"
                value={Number(scopedCalls.length).toLocaleString()}
                icon="call"
                iconClass="icon-blue"
              />
              <MetricCard
                label="Interested Leads"
                value={Number(metrics.interestedLeads || 0).toLocaleString()}
                icon="thumb_up"
                iconClass="icon-green"
              />
              <MetricCard
                label="Answered Calls"
                value={Number(metrics.answeredLeads || 0).toLocaleString()}
                icon="call_received"
                iconClass="icon-teal"
              />
              <MetricCard
                label="Credits Used"
                value={Number(metrics.creditsUsed || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                icon="monetization_on"
                iconClass="icon-orange"
              />
              <MetricCard
                label="Conversion %"
                value={`${conversion}%`}
                icon="trending_up"
                iconClass="icon-purple"
                footer={`Progress ${campaignProgress}%`}
                progress={campaignProgress}
              />
            </div>
          ) : (
            <DashboardKPIs
              interestedLeads={metrics.interestedLeads}
              answeredLeads={metrics.answeredLeads}
              runningCampaigns={metrics.runningCampaigns}
              liveCalls={metrics.liveCalls}
              creditsUsed={metrics.creditsUsed}
              remainingCredits={metrics.remainingCredits}
            />
          )}

          <div className="cl-dashboard-grid cl-mb-section">
            <DashboardAnalytics
              chartData={graphData}
              callsCount={scopedCalls.length || (isCampaignScope ? 0 : totalCalls)}
              period={period}
              onPeriodChange={setPeriod}
            />
            <DashboardActivity activityEvents={activityEvents} liveCalls={metrics.liveCalls} />
          </div>

          {isCampaignScope ? (
            <DashboardInterestedLeads
              calls={scopedCalls}
              onOpenLead={(call) => setDrawerCall(call)}
            />
          ) : (
            <DashboardCampaignTable campaigns={campaignSummary} onCampaignClick={handleCampaignClick} />
          )}
        </>
      )}

      <CallTranscriptDrawer
        isOpen={Boolean(drawerCall)}
        sessionCallId={drawerCall?.session_call_id || null}
        leadName={drawerCall?.name || drawerCall?.lead_name || ''}
        leadData={drawerCall}
        onClose={() => setDrawerCall(null)}
      />

      {confirmStart && (
        <div className="cl-modal-backdrop animate-fade-in" onClick={() => setConfirmStart(null)}>
          <div className="cl-modal animate-scale-up" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', gap: '16px', borderBottom: '1px solid #E2E8F0', paddingBottom: '16px' }}>
              <div style={{
                width: '40px', height: '40px', borderRadius: '10px', background: '#ECFDF5',
                display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#047857', flexShrink: 0,
              }}>
                <span className="material-symbols-outlined">rocket_launch</span>
              </div>
              <div>
                <h3 className="cl-card-title" style={{ fontSize: '16px' }}>Start Outbound Dialer</h3>
                <p className="cl-caption" style={{ color: '#64748B', marginTop: '2px' }}>
                  Campaign: {confirmStart.name}
                </p>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <p className="cl-body" style={{ color: '#374151', margin: 0 }}>
                You are about to launch the outbound dialer now. Please verify parameters:
              </p>

              <div style={{
                background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: '8px',
                padding: '12px', fontSize: '13px', fontFamily: 'monospace',
              }}>
                {[
                  ['Max Concurrency', `${confirmStart.max_concurrent_calls} channels`],
                  ['Calls / Minute', `${confirmStart.calls_per_minute || 10} calls`],
                  ['Attempts Limit', `${confirmStart.max_attempts || 3} attempts`],
                ].map(([k, v]) => (
                  <div key={k} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                    <span style={{ color: '#64748B' }}>{k}:</span>
                    <span style={{ fontWeight: 700, color: '#0F172A' }}>{v}</span>
                  </div>
                ))}
              </div>

              <div className={`cl-compliance-banner ${istStatus.isInside ? 'cl-compliance-banner--active' : 'cl-compliance-banner--inactive'}`}>
                <span className="material-symbols-outlined" style={{ fontSize: '16px', marginRight: '8px' }}>info</span>
                <span>
                  {istStatus.isInside
                    ? `Calling hours are active. Current time: ${istStatus.formatted}.`
                    : `Dialer paused until 9 AM IST. Current time: ${istStatus.formatted}.`}
                </span>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '8px' }}>
              <button className="cl-btn cl-btn--secondary" onClick={() => setConfirmStart(null)}>
                Cancel
              </button>
              <button className="cl-btn cl-btn--primary" onClick={handleConfirmStart}>
                <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>rocket_launch</span>
                Acknowledge & Start
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
