import { useState, useEffect, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useTheme } from '../../hooks/useTheme';
import { useToast } from '../../contexts/ToastContext';
import clientApi from '../../api/client';
import LoaderOverlay from '../../components/shared/LoaderOverlay';
import { ThemeToggle, Button, Card, Badge } from '../../components/shared/ui';

const Dashboard = () => {
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const { showToast } = useToast();
  
  // Real API data & UI State
  const [balance, setBalance] = useState(0);
  const [maxConcurrency, setMaxConcurrency] = useState(5);
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // Credit balance count-up animation state
  const [displayBalance, setDisplayBalance] = useState(0);

  // Resume Confirmation Modal State
  const [confirmStartCampaign, setConfirmStartCampaign] = useState(null);

  const [copiedCampaignId, setCopiedCampaignId] = useState(null);

  const handleCopyCampaignId = (e, id) => {
    e.stopPropagation();
    navigator.clipboard.writeText(id);
    setCopiedCampaignId(id);
    setTimeout(() => setCopiedCampaignId(null), 2000);
  };

  // IST Compliance window state
  const [istStatus, setIstStatus] = useState({ isInside: true, formattedIst: '' });

  useEffect(() => {
    const updateIst = () => {
      const now = new Date();
      // Calculate IST time (UTC +5:30)
      const istTime = new Date(now.getTime() + (now.getTimezoneOffset() * 60000) + (5.5 * 60 * 60 * 1000));
      const hour = istTime.getHours();
      const minutes = istTime.getMinutes();
      const isInside = hour >= 9 && hour < 21;
      
      const ampm = hour >= 12 ? 'PM' : 'AM';
      const displayHour = hour % 12 || 12;
      const displayMin = minutes < 10 ? '0' + minutes : minutes;
      
      setIstStatus({
        isInside,
        formattedIst: `${displayHour}:${displayMin} ${ampm} IST`
      });
    };

    updateIst();
    const interval = setInterval(updateIst, 30000);
    return () => clearInterval(interval);
  }, []);



  // Load dashboard data
  const loadDashboardData = useCallback(async () => {
    setLoading(true);
    try {
      // 1. Fetch credits
      const creditsRes = await clientApi.get('/api/credits');
      if (creditsRes.data) {
        setBalance(creditsRes.data.balance_credits || 0);
        setMaxConcurrency(creditsRes.data.max_concurrent_calls || 5);
      }
    } catch (err) {
      console.warn('Could not fetch credit balance from API.', err);
    }

    try {
      // 2. Fetch campaigns list
      const campaignsRes = await clientApi.get('/api/campaigns');
      if (campaignsRes.data && campaignsRes.data.campaigns) {
        setCampaigns(campaignsRes.data.campaigns);
      } else {
        setCampaigns([]);
      }
    } catch (err) {
      console.warn('Could not list campaigns from API.', err);
      setCampaigns([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Async load effect
  useEffect(() => {
    const timer = setTimeout(() => {
      loadDashboardData();
    }, 0);
    return () => clearTimeout(timer);
  }, [loadDashboardData]);

  // Real-time polling for active/pausing campaigns
  useEffect(() => {
    const needsPolling = campaigns.some(c => 
      c.status === 'running' || c.status === 'pausing' || (c.status === 'paused' && c.calling_leads > 0)
    );
    if (!needsPolling) return;
    
    const interval = setInterval(() => {
      loadDashboardData();
    }, 5000);
    return () => clearInterval(interval);
  }, [campaigns, loadDashboardData]);

  // Credit Balance Count Up Animation
  useEffect(() => {
    let start = 0;
    const end = balance;
    if (end === 0) return;

    const duration = 1500;
    const startTime = performance.now();

    const update = (currentTime) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const easedProgress = 1 - Math.pow(1 - progress, 3); // cubic-out
      const current = start + (end - start) * easedProgress;

      setDisplayBalance(current);

      if (progress < 1) {
        requestAnimationFrame(update);
      }
    };

    requestAnimationFrame(update);
  }, [balance]);

  // Campaign State Control handlers (Real API bindings + fallback simulation)
  const handleToggleState = async (campaignId, currentStatus) => {
    const action = currentStatus === 'running' ? 'stop' : 'start';
    if (action === 'start') {
      const camp = campaigns.find(c => c.id === campaignId);
      setConfirmStartCampaign(camp);
      return;
    }

    try {
      const response = await clientApi.patch(`/api/campaigns/${campaignId}/stop`);
      if (response.data) {
        showToast('Campaign paused successfully.', 'success');
        loadDashboardData();
        return;
      }
    } catch (err) {
      console.error('Failed to toggle campaign status', err);
      showToast(err.customErrorMessage || 'Failed to toggle campaign status', 'error');
    }
  };

  const handleConfirmStart = async () => {
    if (!confirmStartCampaign) return;
    const campaignId = confirmStartCampaign.id;
    try {
      const response = await clientApi.patch(`/api/campaigns/${campaignId}/start`);
      if (response.data) {
        showToast('Campaign started successfully.', 'success');
        setConfirmStartCampaign(null);
        loadDashboardData();
        return;
      }
    } catch (err) {
      console.error('Failed to start campaign', err);
      showToast(err.customErrorMessage || 'Failed to start campaign', 'error');
    }
  };

  const handleSignOut = () => {
    localStorage.removeItem('client_api_key');
    navigate('/login');
  };

  // Helper formatting INR
  const formatINR = (value) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 2
    }).format(value);
  };

  const isPausing = campaigns.some(c => c.status === 'pausing' || (c.status === 'paused' && c.calling_leads > 0));

  return (
    <>
          <LoaderOverlay isVisible={isPausing} message="Finishing ongoing leads..." />
          
          {/* Calling Window Compliance Banner */}
          <div className={`mb-stack-lg p-4 rounded-xl border border-l-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 transition-all duration-300 animate-fade-in ${
            istStatus.isInside 
              ? 'bg-emerald-500/[0.07] dark:bg-emerald-500/[0.03] border-emerald-500/25 dark:border-emerald-500/15 border-l-emerald-500 text-emerald-800 dark:text-emerald-300' 
              : 'bg-amber-500/[0.07] dark:bg-amber-500/[0.03] border-amber-500/25 dark:border-amber-500/15 border-l-amber-500 text-amber-800 dark:text-amber-300'
          }`}>
            <div className="flex items-start gap-3">
              <div className="mt-1 shrink-0 flex items-center">
                {istStatus.isInside ? (
                  <span className="relative flex h-3 w-3">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
                  </span>
                ) : (
                  <span className="relative flex h-3 w-3">
                    <span className="animate-pulse absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-3 w-3 bg-amber-500"></span>
                  </span>
                )}
              </div>
              <div>
                <h4 className="font-bold text-sm tracking-wide uppercase flex items-center gap-2">
                  {istStatus.isInside ? 'Calling Window Active' : 'Calling Window Paused (TRAI Compliance)'}
                  <span className="text-xs px-2 py-0.5 rounded bg-surface/50 dark:bg-molten-bg/50 border border-current/10 font-mono font-medium">
                    {istStatus.formattedIst}
                  </span>
                </h4>
                <p className="text-xs mt-1 opacity-90 leading-relaxed max-w-3xl">
                  {istStatus.isInside 
                    ? 'The compliant calling hours (9:00 AM – 9:00 PM IST) are active. Outbound campaigns are permitted to dial normally.' 
                    : 'We are currently outside the TRAI-compliant hours (9:00 AM – 9:00 PM IST). Automated dialing is paused and will automatically resume at 9:00 AM IST tomorrow. You can still safely start campaigns, upload leads, or adjust settings now.'}
                </p>
              </div>
            </div>
            <div className="shrink-0 flex items-center gap-2 text-xs font-semibold px-3 py-1.5 rounded-lg bg-surface/40 dark:bg-black/10 border border-current/10 font-mono">
              <span className="material-symbols-outlined text-[16px]">schedule</span>
              9 AM - 9 PM IST enforced
            </div>
          </div>

          {/* Credit Balance Section */}
          <section className="mb-stack-lg animate-fade-in">
            <div className="bg-arctic-surface dark:bg-molten-surface p-6 rounded-xl border border-outline-variant/50 dark:border-[#2A345E]/50 shadow-md relative overflow-hidden group transition-all duration-300">
              <div className="absolute top-0 right-0 p-6 opacity-10 group-hover:opacity-20 transition-opacity pointer-events-none">
                <span className="material-symbols-outlined text-[120px]">account_balance_wallet</span>
              </div>
              <p className="text-arctic-text-muted dark:text-molten-text-muted font-label-md text-label-md mb-2">Prepaid Credit Balance</p>
              <h1 className="font-headline-xl text-headline-xl text-primary dark:text-molten-primary tabular-nums">
                {formatINR(displayBalance)}
              </h1>
              <div className="mt-6 flex flex-wrap gap-4 relative z-10">
                {/* TODO: Credit recharge/top-up (Razorpay integration Phase 5)
                <Button variant="primary" className="!bg-primary-container !text-on-primary-container !px-6 !py-2" icon="add">
                  Top Up
                </Button>
                */}
                {/* TODO: Billing history
                <Button variant="outline" className="!px-6 !py-2">
                  View Billing History
                </Button>
                */}
              </div>
            </div>
          </section>



          {/* Campaign Grid */}
          <div className="flex items-center justify-between mb-stack-md animate-fade-in" style={{ animationDelay: '0.2s' }}>
            <h2 className="font-headline-md text-headline-md">Active Campaigns</h2>
            {/* TODO: View All Campaigns page
            <button className="text-primary dark:text-molten-primary font-bold flex items-center gap-1 hover:underline cursor-pointer">
              View All <span className="material-symbols-outlined">chevron_right</span>
            </button>
            */}
          </div>

          <LoaderOverlay isVisible={loading} message="Loading Campaigns..." />
          {!loading && (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-gutter animate-fade-in" style={{ animationDelay: '0.3s' }}>
              {campaigns.length === 0 ? (
                <div className="col-span-full flex flex-col items-center justify-center p-12 bg-arctic-surface dark:bg-molten-surface border border-dashed border-outline-variant dark:border-[#2A345E] rounded-xl text-center">
                  <div className="w-16 h-16 bg-primary/10 dark:bg-molten-primary/10 text-primary dark:text-molten-primary rounded-full flex items-center justify-center mb-4">
                    <span className="material-symbols-outlined text-3xl">campaign</span>
                  </div>
                  <h3 className="text-xl font-bold mb-2">No Campaigns Yet</h3>
                  <p className="text-arctic-text-muted dark:text-molten-text-muted max-w-md mb-6">
                    You haven't created any campaigns. Click the "Create Campaign" button in the sidebar to get started and launch your first AI calling queue.
                  </p>
                </div>
              ) : (
                campaigns.map((camp) => {
                  if (camp.status === 'running') {
                    // Running Campaign (Special effect rotating border)
                    const progressPercentage = camp.total_leads > 0 
                      ? Math.round(((camp.total_leads - camp.calling_leads) / camp.total_leads) * 100) 
                      : 85; // Default from proto

                    return (
                      <div key={camp.id} className="animated-border rounded-xl p-[2px] cursor-pointer" onClick={() => window.location.href = `/app/campaigns/${camp.id}`}>
                        <div className="bg-arctic-surface dark:bg-molten-surface p-5 h-full relative z-10 rounded-[10px] flex flex-col justify-between transition-all duration-300 shadow-sm">
                          <div>
                            <div className="flex justify-between items-start mb-4">
                              <Badge status={camp.status} />
                              <div className="flex gap-2">
                                <button 
                                  onClick={(e) => { e.stopPropagation(); handleToggleState(camp.id, 'running'); }}
                                  className="p-1 hover:bg-surface-variant/20 rounded-md text-primary dark:text-molten-primary cursor-pointer"
                                  title="Pause Campaign"
                                >
                                  <span className="material-symbols-outlined">pause_circle</span>
                                </button>
                                <button className="p-1 hover:bg-surface-container rounded-md" onClick={(e) => e.stopPropagation()}>
                                  <span className="material-symbols-outlined">more_vert</span>
                                </button>
                              </div>
                            </div>
                            <h3 className="font-headline-sm text-headline-sm mb-1">{camp.name}</h3>
                            <div className="flex items-center gap-1.5 mb-3 group/uuid w-fit" onClick={(e) => handleCopyCampaignId(e, camp.id)}>
                              <span className="text-xs text-on-surface-variant/70 dark:text-molten-text-muted font-mono select-all">
                                ID: {camp.id.substring(0, 8)}...
                              </span>
                              <button 
                                className="opacity-0 group-hover/uuid:opacity-100 p-0.5 hover:bg-surface-container dark:hover:bg-[#2A345E]/50 rounded text-on-surface-variant dark:text-molten-text transition-all flex items-center"
                                title="Copy Full Campaign UUID"
                              >
                                <span className="material-symbols-outlined text-[12px]">
                                  {copiedCampaignId === camp.id ? 'check' : 'content_copy'}
                                </span>
                              </button>
                            </div>
                            <p className="text-arctic-text-muted dark:text-molten-text-muted text-body-sm mb-6">
                              {camp.description || 'Campaign outbound calling process active.'}
                            </p>
                          </div>
                          <div className="space-y-3 border-t border-outline-variant dark:border-[#2A345E] pt-4">
                            <div className="flex justify-between text-body-sm">
                              <span className="text-arctic-text-muted">Concurrency</span>
                              <span className="font-bold tabular-nums">{camp.calling_leads || camp.max_concurrent_calls}/{camp.max_concurrent_calls}</span>
                            </div>
                            <div className="w-full bg-surface-container dark:bg-surface-variant/20 h-1.5 rounded-full overflow-hidden">
                              <div className="bg-primary dark:bg-molten-primary h-full transition-all duration-500" style={{ width: `${progressPercentage}%` }}></div>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  } else if (camp.status === 'paused') {
                    // Paused Campaign
                    return (
                      <div key={camp.id} className="bg-arctic-surface dark:bg-molten-surface p-5 rounded-xl border border-outline-variant/50 dark:border-[#2A345E]/50 shadow-sm hover:shadow-md transition-all duration-300 flex flex-col justify-between cursor-pointer" onClick={() => window.location.href = `/app/campaigns/${camp.id}`}>
                        <div>
                          <div className="flex justify-between items-start mb-4">
                            <Badge status={camp.status} />
                            <button className="p-1 hover:bg-surface-container rounded-md" onClick={(e) => e.stopPropagation()}>
                              <span className="material-symbols-outlined">more_vert</span>
                            </button>
                          </div>
                          <h3 className="font-headline-sm text-headline-sm mb-1">{camp.name}</h3>
                          <div className="flex items-center gap-1.5 mb-3 group/uuid w-fit" onClick={(e) => handleCopyCampaignId(e, camp.id)}>
                            <span className="text-xs text-on-surface-variant/70 dark:text-molten-text-muted font-mono select-all">
                              ID: {camp.id.substring(0, 8)}...
                            </span>
                            <button 
                              className="opacity-0 group-hover/uuid:opacity-100 p-0.5 hover:bg-surface-container dark:hover:bg-[#2A345E]/50 rounded text-on-surface-variant dark:text-molten-text transition-all flex items-center"
                              title="Copy Full Campaign UUID"
                            >
                              <span className="material-symbols-outlined text-[12px]">
                                {copiedCampaignId === camp.id ? 'check' : 'content_copy'}
                              </span>
                            </button>
                          </div>
                          <p className="text-arctic-text-muted dark:text-molten-text-muted text-body-sm mb-6">
                            {camp.description || 'Campaign outbound calling process paused.'}
                          </p>
                        </div>
                        <div className="space-y-3 border-t border-outline-variant dark:border-[#2A345E] pt-4">
                          <div className="flex justify-between text-body-sm">
                            <span className="text-arctic-text-muted">Completed Leads</span>
                            <span className="font-bold tabular-nums">{camp.completed_leads}</span>
                          </div>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleToggleState(camp.id, 'paused'); }}
                            className="w-full mt-2 py-2 border border-primary text-primary dark:border-molten-primary dark:text-molten-primary rounded-lg font-bold hover:bg-primary/5 transition-colors cursor-pointer"
                          >
                            Resume Campaign
                          </button>
                        </div>
                      </div>
                    );
                  } else {
                    // Draft/Completed/Other Campaign
                    const isCompleted = camp.status === 'completed';
                    const isFailed = camp.status === 'failed';
                    
                    let badgeClasses = 'bg-arctic-text-muted/15 text-arctic-text-muted';
                    if (isCompleted) badgeClasses = 'bg-secondary/15 text-secondary dark:bg-molten-success/15 dark:text-molten-success';
                    if (isFailed) badgeClasses = 'bg-error/15 text-error dark:bg-molten-error/15 dark:text-molten-error';

                    return (
                      <div key={camp.id} className="bg-arctic-surface dark:bg-molten-surface p-5 rounded-xl border border-outline-variant/50 dark:border-[#2A345E]/50 shadow-sm hover:shadow-md transition-all duration-300 flex flex-col justify-between cursor-pointer" onClick={() => window.location.href = `/app/campaigns/${camp.id}`}>
                        <div>
                          <div className="flex justify-between items-start mb-4">
                            <Badge status={camp.status} />
                            <button className="p-1 hover:bg-surface-container rounded-md" onClick={(e) => e.stopPropagation()}>
                              <span className="material-symbols-outlined">more_vert</span>
                            </button>
                          </div>
                          <h3 className="font-headline-sm text-headline-sm mb-1">{camp.name}</h3>
                          <div className="flex items-center gap-1.5 mb-3 group/uuid w-fit" onClick={(e) => handleCopyCampaignId(e, camp.id)}>
                            <span className="text-xs text-on-surface-variant/70 dark:text-molten-text-muted font-mono select-all">
                              ID: {camp.id.substring(0, 8)}...
                            </span>
                            <button 
                              className="opacity-0 group-hover/uuid:opacity-100 p-0.5 hover:bg-surface-container dark:hover:bg-[#2A345E]/50 rounded text-on-surface-variant dark:text-molten-text transition-all flex items-center"
                              title="Copy Full Campaign UUID"
                            >
                              <span className="material-symbols-outlined text-[12px]">
                                {copiedCampaignId === camp.id ? 'check' : 'content_copy'}
                              </span>
                            </button>
                          </div>
                          <p className="text-arctic-text-muted dark:text-molten-text-muted text-body-sm mb-6">
                            {camp.description || 'Campaign configurations in progress.'}
                          </p>
                        </div>
                        <div className="space-y-3 border-t border-outline-variant dark:border-[#2A345E] pt-4">
                          <div className="flex justify-between text-body-sm">
                            <span className="text-arctic-text-muted">Budget Credits</span>
                            <span className="font-bold">{camp.budget_credits} cr</span>
                          </div>
                          <button className="w-full mt-2 py-2 bg-surface-container-high dark:bg-surface-variant/30 text-on-surface dark:text-molten-text rounded-lg font-bold hover:brightness-95 transition-colors cursor-pointer">
                            {camp.status === 'draft' ? 'Complete Setup' : 'View Stats'}
                          </button>
                        </div>
                      </div>
                    );
                  }
                })
              )}
            </div>
          )}

      {/* Resume Campaign Confirmation Modal */}
      {confirmStartCampaign && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-[#0c1941]/40 dark:bg-black/60 backdrop-blur-sm animate-fade-in" onClick={() => setConfirmStartCampaign(null)}></div>
          <div className="relative bg-arctic-surface dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-5 text-on-surface dark:text-molten-text animate-scale-up">
            
            {/* Modal Header */}
            <div className="flex items-center gap-3 border-b border-outline-variant dark:border-[#2A345E] pb-3">
              <div className="w-10 h-10 rounded-full bg-primary/10 dark:bg-molten-primary/10 text-primary dark:text-molten-primary flex items-center justify-center shrink-0">
                <span className="material-symbols-outlined text-[24px] animate-pulse">play_circle</span>
              </div>
              <div>
                <h3 className="text-lg font-bold">Start Outbound Dialer</h3>
                <p className="text-xs text-arctic-text-muted dark:text-molten-text-muted">Campaign: {confirmStartCampaign.name}</p>
              </div>
            </div>

            {/* Warning Message / Details */}
            <div className="space-y-3">
              <p className="text-sm opacity-90 leading-relaxed">
                You are about to launch the outbound dialer queue. Please verify compliance and resource parameters:
              </p>
              
              {/* Campaign stats preview */}
              <div className="bg-surface-container-low dark:bg-[#1A1C24] border border-outline-variant/60 dark:border-[#2A345E] rounded-xl p-3 text-xs space-y-2 font-mono">
                <div className="flex justify-between">
                  <span className="text-arctic-text-muted dark:text-molten-text-muted">Max Concurrency:</span>
                  <span className="font-bold">{confirmStartCampaign.max_concurrent_calls} channels</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-arctic-text-muted dark:text-molten-text-muted">Calls / Minute:</span>
                  <span className="font-bold">{confirmStartCampaign.calls_per_minute || 10} calls</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-arctic-text-muted dark:text-molten-text-muted">Attempts Limit:</span>
                  <span className="font-bold">{confirmStartCampaign.max_attempts || 3} attempts</span>
                </div>
              </div>

              {/* Compliance Warning Banner */}
              <div className={`p-3 rounded-xl border flex gap-3 text-xs ${
                istStatus.isInside 
                  ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-800 dark:text-emerald-400' 
                  : 'bg-amber-500/10 border-amber-500/20 text-amber-800 dark:text-amber-400'
              }`}>
                <span className="material-symbols-outlined shrink-0 text-[18px]">info</span>
                <div>
                  <p className="font-bold uppercase tracking-wider mb-0.5">
                    {istStatus.isInside ? 'Calling Hours Active' : 'Calling Hours Restricted'}
                  </p>
                  <p className="opacity-90">
                    {istStatus.isInside 
                      ? `Outbound dialing is allowed. Current time is ${istStatus.formattedIst}.` 
                      : `Dialer is paused until 9 AM IST. Current time is ${istStatus.formattedIst}. Calls will queue automatically.`}
                  </p>
                </div>
              </div>
            </div>

            {/* Modal Buttons */}
            <div className="flex justify-end gap-2 pt-2 border-t border-outline-variant dark:border-[#2A345E]">
              <button
                type="button"
                onClick={() => setConfirmStartCampaign(null)}
                className="px-4 py-2 text-on-surface-variant dark:text-molten-text-muted border border-outline-variant dark:border-[#2A345E] hover:bg-surface-container dark:hover:bg-[#2A345E]/50 rounded-lg cursor-pointer transition-colors text-sm font-semibold"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmStart}
                className="px-5 py-2 bg-primary dark:bg-molten-primary text-on-primary dark:text-molten-bg rounded-lg cursor-pointer font-bold hover:brightness-110 transition-all text-sm flex items-center gap-1.5"
              >
                <span className="material-symbols-outlined text-[18px]">rocket_launch</span>
                Acknowledge & Start
              </button>
            </div>

          </div>
        </div>
      )}
    </>
  );
};

export default Dashboard;
