import { useState, useEffect, useCallback } from 'react';
import { useTheme } from '../../hooks/useTheme';
import clientApi from '../../api/client';
import LoaderOverlay from '../../components/shared/LoaderOverlay';
import { ThemeToggle, Button, Card, Badge } from '../../components/shared/ui';

// Generate local campaign ID outside render block to ensure purity
const generateLocalId = () => `campaign-local-${Date.now()}`;

const Dashboard = () => {
  const { theme, toggleTheme } = useTheme();
  
  // Real API data & UI State
  const [balance, setBalance] = useState(0);
  const [maxConcurrency, setMaxConcurrency] = useState(5);
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // Credit balance count-up animation state
  const [displayBalance, setDisplayBalance] = useState(0);

  // Wizard State
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [wizardStep, setWizardStep] = useState(1);
  const [newCampaign, setNewCampaign] = useState({
    name: '',
    bot_config_id: 'sales-specialist-uuid',
    budget_credits: 1000,
    max_concurrent_calls: 5,
  });

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
      console.warn('Could not fetch credit balance from API, falling back to mock balance.', err);
      setBalance(48250.00); // Mock default balance from prototype
    }

    try {
      // 2. Fetch campaigns list
      const campaignsRes = await clientApi.get('/api/campaigns');
      let apiCampaigns = [];
      if (campaignsRes.data && campaignsRes.data.campaigns) {
        apiCampaigns = campaignsRes.data.campaigns;
      }
      
      // Load locally created campaigns if any (for mock capability when POST /api/campaigns isn't accessible)
      const localCamps = JSON.parse(localStorage.getItem('local_campaigns') || '[]');
      
      // Merge: priority to apiCampaigns, append localCamps that aren't in API list
      const merged = [...apiCampaigns];
      localCamps.forEach(lc => {
        if (!merged.some(mc => mc.id === lc.id)) {
          merged.push(lc);
        }
      });
      
      // Ensure we have a robust set of prototype campaigns for UI demonstration
      const defaultCampaigns = [
        {
          id: 'campaign-1-uuid',
          name: 'Q4 Real Estate Outreach',
          status: 'running',
          description: 'Automated cold-calling for luxury properties in Mumbai region.',
          total_leads: 1200,
          calling_leads: 85,
          completed_leads: 450,
          failed_leads: 15,
          budget_credits: 5000,
          budget_used_credits: 1250,
          max_concurrent_calls: 100
        },
        {
          id: 'campaign-2-uuid',
          name: 'SaaS Demo Follow-up',
          status: 'paused',
          description: 'Voice AI feedback collection for Tier 1 enterprise leads.',
          total_leads: 2450,
          calling_leads: 0,
          completed_leads: 1204,
          failed_leads: 50,
          budget_credits: 10000,
          budget_used_credits: 4890,
          max_concurrent_calls: 10
        },
        {
          id: 'campaign-3-uuid',
          name: 'Holiday Season Greetings',
          status: 'draft',
          description: 'Personalized holiday wishes for active loyalty members.',
          total_leads: 5000,
          calling_leads: 0,
          completed_leads: 0,
          failed_leads: 0,
          budget_credits: 3000,
          budget_used_credits: 0,
          max_concurrent_calls: 5,
          scheduled_date: 'Dec 20, 2026'
        },
        {
          id: 'campaign-4-uuid',
          name: 'Overdue Invoice Reminders',
          status: 'completed',
          description: 'Gentle nudges for accounts 30+ days past due.',
          total_leads: 850,
          calling_leads: 0,
          completed_leads: 820,
          failed_leads: 30,
          budget_credits: 2000,
          budget_used_credits: 1950,
          max_concurrent_calls: 20
        },
        {
          id: 'campaign-5-uuid',
          name: 'VIP Welcome Calls',
          status: 'running',
          description: 'Onboarding guidance for new premium tier signups.',
          total_leads: 45,
          calling_leads: 5,
          completed_leads: 12,
          failed_leads: 0,
          budget_credits: 1000,
          budget_used_credits: 120,
          max_concurrent_calls: 5
        },
        {
          id: 'campaign-6-uuid',
          name: 'Lead Re-engagement',
          status: 'failed',
          description: 'Attempting to contact unresponsive leads from Q2.',
          total_leads: 3000,
          calling_leads: 0,
          completed_leads: 150,
          failed_leads: 2850,
          budget_credits: 6000,
          budget_used_credits: 400,
          max_concurrent_calls: 50
        }
      ];

      // Auto-inject missing prototypes
      defaultCampaigns.forEach(dc => {
        if (!merged.some(mc => mc.id === dc.id)) {
          merged.push(dc);
        }
      });
      
      setCampaigns(merged);
      localStorage.setItem('local_campaigns', JSON.stringify(merged));
    } catch (err) {
      console.warn('Could not list campaigns from API, using cached data.', err);
      const localCamps = JSON.parse(localStorage.getItem('local_campaigns') || '[]');
      
      const defaultCampaigns = [
        {
          id: 'campaign-1-uuid',
          name: 'Q4 Real Estate Outreach',
          status: 'running',
          description: 'Automated cold-calling for luxury properties in Mumbai region.',
          total_leads: 1200,
          calling_leads: 85,
          completed_leads: 450,
          failed_leads: 15,
          budget_credits: 5000,
          budget_used_credits: 1250,
          max_concurrent_calls: 100
        },
        {
          id: 'campaign-2-uuid',
          name: 'SaaS Demo Follow-up',
          status: 'paused',
          description: 'Voice AI feedback collection for Tier 1 enterprise leads.',
          total_leads: 2450,
          calling_leads: 0,
          completed_leads: 1204,
          failed_leads: 50,
          budget_credits: 10000,
          budget_used_credits: 4890,
          max_concurrent_calls: 10
        },
        {
          id: 'campaign-3-uuid',
          name: 'Holiday Season Greetings',
          status: 'draft',
          description: 'Personalized holiday wishes for active loyalty members.',
          total_leads: 5000,
          calling_leads: 0,
          completed_leads: 0,
          failed_leads: 0,
          budget_credits: 3000,
          budget_used_credits: 0,
          max_concurrent_calls: 5,
          scheduled_date: 'Dec 20, 2026'
        },
        {
          id: 'campaign-4-uuid',
          name: 'Overdue Invoice Reminders',
          status: 'completed',
          description: 'Gentle nudges for accounts 30+ days past due.',
          total_leads: 850,
          calling_leads: 0,
          completed_leads: 820,
          failed_leads: 30,
          budget_credits: 2000,
          budget_used_credits: 1950,
          max_concurrent_calls: 20
        },
        {
          id: 'campaign-5-uuid',
          name: 'VIP Welcome Calls',
          status: 'running',
          description: 'Onboarding guidance for new premium tier signups.',
          total_leads: 45,
          calling_leads: 5,
          completed_leads: 12,
          failed_leads: 0,
          budget_credits: 1000,
          budget_used_credits: 120,
          max_concurrent_calls: 5
        },
        {
          id: 'campaign-6-uuid',
          name: 'Lead Re-engagement',
          status: 'failed',
          description: 'Attempting to contact unresponsive leads from Q2.',
          total_leads: 3000,
          calling_leads: 0,
          completed_leads: 150,
          failed_leads: 2850,
          budget_credits: 6000,
          budget_used_credits: 400,
          max_concurrent_calls: 50
        }
      ];

      defaultCampaigns.forEach(dc => {
        if (!localCamps.some(mc => mc.id === dc.id)) {
          localCamps.push(dc);
        }
      });

      setCampaigns(localCamps);
      localStorage.setItem('local_campaigns', JSON.stringify(localCamps));
    } finally {
      setLoading(false);
    }
  }, []);

  // Async load effect to prevent synchronous setState linting warning
  useEffect(() => {
    const timer = setTimeout(() => {
      loadDashboardData();
    }, 0);
    return () => clearTimeout(timer);
  }, [loadDashboardData]);

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
  const handleToggleCampaign = async (campaignId, currentStatus) => {
    const action = currentStatus === 'running' ? 'stop' : 'start';
    try {
      const response = await clientApi.patch(`/api/campaigns/${campaignId}/${action}`);
      if (response.data) {
        loadDashboardData();
        return;
      }
    } catch (err) {
      console.warn(`API campaign ${action} failed. Simulating locally.`, err);
    }

    // Local Fallback simulation
    const updated = campaigns.map(camp => {
      if (camp.id === campaignId) {
        return {
          ...camp,
          status: currentStatus === 'running' ? 'paused' : 'running',
          calling_leads: currentStatus === 'running' ? 0 : Math.round(camp.total_leads * 0.8 || 20)
        };
      }
      return camp;
    });
    setCampaigns(updated);
    localStorage.setItem('local_campaigns', JSON.stringify(updated));
  };

  const handleCreateCampaign = async () => {
    if (!newCampaign.name.trim()) return;

    try {
      // Try calling admin internal/campaigns route if accessible or client-side POST /api/campaigns
      const response = await clientApi.post('/api/campaigns', newCampaign);
      if (response.data) {
        setIsWizardOpen(false);
        resetWizard();
        loadDashboardData();
        return;
      }
    } catch (err) {
      console.warn('API campaign creation failed. Saving locally to simulate.', err);
    }

    // Local Simulation creation using pure generator
    const generatedId = generateLocalId();
    const newCampObj = {
      id: generatedId,
      name: newCampaign.name,
      status: 'draft',
      description: newCampaign.bot_config_id === 'sales-specialist-uuid'
        ? 'Sales Specialist persona. High energy, persuasive outbound calling.'
        : 'Support Guide persona. Calm, helpful, patient query resolution.',
      total_leads: 0,
      calling_leads: 0,
      completed_leads: 0,
      failed_leads: 0,
      budget_credits: Number(newCampaign.budget_credits),
      budget_used_credits: 0,
      max_concurrent_calls: Number(newCampaign.max_concurrent_calls)
    };

    const updatedList = [newCampObj, ...campaigns];
    setCampaigns(updatedList);
    localStorage.setItem('local_campaigns', JSON.stringify(updatedList));
    
    setIsWizardOpen(false);
    resetWizard();
  };

  const resetWizard = () => {
    setWizardStep(1);
    setNewCampaign({
      name: '',
      bot_config_id: 'sales-specialist-uuid',
      budget_credits: 1000,
      max_concurrent_calls: 5,
    });
  };

  const handleSignOut = () => {
    localStorage.removeItem('client_api_key');
    window.location.href = '/login';
  };

  // Helper formatting INR
  const formatINR = (value) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 2
    }).format(value);
  };

  return (
    <div className="bg-arctic-bg dark:bg-molten-bg text-on-surface dark:text-molten-text min-h-screen font-body-md selection:bg-primary/20 transition-colors duration-500">
      
      {/* TopNavBar */}
      <header className="fixed top-0 w-full z-50 bg-arctic-surface dark:bg-molten-surface border-b border-outline-variant dark:border-[#2A345E] shadow-[0_4px_20px_rgba(22,71,232,0.05)] dark:shadow-none transition-colors duration-500">
        <div className="flex justify-between items-center h-16 px-margin-desktop w-full">
          <div className="flex items-center gap-8">
            <span className="font-headline-md text-headline-md font-extrabold text-primary dark:text-molten-primary">
              Aakashvani
            </span>
            {/* Top nav links removed — navigation handled via sidebar */}
          </div>
          <div className="flex items-center gap-4">
            <ThemeToggle />
            <button className="p-2 rounded-full hover:bg-surface-variant/20 transition-colors relative cursor-pointer">
              <span className="material-symbols-outlined">notifications</span>
              <span className="absolute top-2 right-2 w-2 h-2 bg-error rounded-full animate-ping"></span>
            </button>
            <div className="h-8 w-8 rounded-full overflow-hidden border border-outline-variant">
              <img
                alt="User Profile"
                src="https://lh3.googleusercontent.com/aida-public/AB6AXuB-aNsyul0D2XuibnrCoFQwP5pIUfGHqxcak3PpTb-dmsFIUzD9q4o_-jvZjxMmHvm2B0_zJ-fhDHzvF6TgTn4jHDJIb0ZP9-MECYYJ-Ht1TjM2O1Z49-9kSSKRR5ZcPQ_liEuOiVci65tCEAPYuytigpMcGGR13VZv2CSLLXsrm1heV6vMgHgtFnUdf5XpliAVvZBM5flTMAMzRzqgPfh3Zc9lWPIhCbViG61_wT24edLOJHutfQAaHDiVi_Kp6u_UaQnLaOphSRQ"
                className="object-cover h-full w-full"
              />
            </div>
          </div>
        </div>
      </header>

      {/* SideNav (Desktop) */}
      <aside className="fixed left-0 top-16 h-[calc(100vh-64px)] w-64 bg-arctic-bg dark:bg-molten-bg border-r border-outline-variant dark:border-[#2A345E] hidden lg:flex flex-col p-4 space-y-2 transition-colors duration-500">
        <div className="mb-6 px-4 py-2">
          <h2 className="font-headline-sm text-headline-sm font-bold text-on-surface dark:text-molten-text">Aakashvani Ops</h2>
          <p className="font-body-sm text-body-sm text-arctic-text-muted dark:text-molten-text-muted">AI Voice Platform</p>
        </div>
        <nav className="space-y-1 flex-grow">
          <a className="flex items-center gap-3 bg-primary-container dark:bg-tertiary-container text-on-primary-container dark:text-on-tertiary-container rounded-lg px-4 py-3 font-bold active:scale-[0.98] transition-all" href="#">
            <span className="material-symbols-outlined">dashboard</span>
            <span className="font-label-md text-label-md">Dashboard</span>
          </a>
          {/* TODO: Phase 3 analytics
          <a className="flex items-center gap-3 text-arctic-text-muted dark:text-molten-text-muted px-4 py-3 hover:bg-surface-container dark:hover:bg-surface-variant/10 hover:translate-x-1 rounded-lg transition-all" href="#">
            <span className="material-symbols-outlined">leaderboard</span>
            <span className="font-label-md text-label-md">Analytics</span>
          </a>
          */}
          <a className="flex items-center gap-3 text-arctic-text-muted dark:text-molten-text-muted px-4 py-3 hover:bg-surface-container dark:hover:bg-surface-variant/10 hover:translate-x-1 rounded-lg transition-all" href="/app/calls">
            <span className="material-symbols-outlined">description</span>
            <span className="font-label-md text-label-md">Logs</span>
          </a>
          {/* TODO: Security settings
          <a className="flex items-center gap-3 text-arctic-text-muted dark:text-molten-text-muted px-4 py-3 hover:bg-surface-container dark:hover:bg-surface-variant/10 hover:translate-x-1 rounded-lg transition-all" href="#">
            <span className="material-symbols-outlined">security</span>
            <span className="font-label-md text-label-md">Security</span>
          </a>
          */}
        </nav>
        {/* TODO: Phase 2/3 campaign creation
        <Button
          onClick={() => setIsWizardOpen(true)}
          className="w-full shadow-lg shadow-primary/20 py-3 font-bold"
          icon="add_circle"
        >
          New Campaign
        </Button>
        */}
        <div className="pt-4 border-t border-outline-variant dark:border-[#2A345E] space-y-1">
          {/* TODO: Support page
          <a className="flex items-center gap-3 text-arctic-text-muted dark:text-molten-text-muted px-4 py-3 hover:bg-surface-container dark:hover:bg-surface-variant/10 rounded-lg transition-all" href="#">
            <span className="material-symbols-outlined">help</span>
            <span className="font-label-md text-label-md">Support</span>
          </a>
          */}
          <button
            onClick={handleSignOut}
            className="w-full flex items-center gap-3 text-arctic-text-muted dark:text-molten-text-muted px-4 py-3 hover:bg-surface-container dark:hover:bg-surface-variant/10 rounded-lg transition-all cursor-pointer text-left"
          >
            <span className="material-symbols-outlined">logout</span>
            <span className="font-label-md text-label-md">Sign Out</span>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="lg:ml-64 pt-24 px-margin-mobile md:px-margin-desktop pb-24">
        <div className="max-w-container-max mx-auto">
          
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

          {/* Quick Stats */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-gutter mb-stack-lg animate-fade-in" style={{ animationDelay: '0.1s' }}>
            <div className="bg-arctic-surface dark:bg-molten-surface p-5 rounded-lg border border-outline-variant/50 dark:border-[#2A345E]/50 shadow-sm hover:shadow-md transition-all duration-300">
              <div className="flex items-center justify-between mb-4">
                <span className="material-symbols-outlined text-primary dark:text-molten-primary">call</span>
                <span className="text-arctic-warning font-bold text-label-sm">+12%</span>
              </div>
              <p className="text-arctic-text-muted dark:text-molten-text-muted font-label-sm uppercase tracking-wider mb-1">Total Minutes</p>
              <p className="font-headline-md text-headline-md tabular-nums">142,840</p>
            </div>
            <div className="bg-arctic-surface dark:bg-molten-surface p-5 rounded-lg border border-outline-variant/50 dark:border-[#2A345E]/50 shadow-sm hover:shadow-md transition-all duration-300">
              <div className="flex items-center justify-between mb-4">
                <span className="material-symbols-outlined text-primary dark:text-molten-primary">record_voice_over</span>
                <span className="text-arctic-warning font-bold text-label-sm">+8%</span>
              </div>
              <p className="text-arctic-text-muted dark:text-molten-text-muted font-label-sm uppercase tracking-wider mb-1">Active Bots</p>
              <p className="font-headline-md text-headline-md tabular-nums">24</p>
            </div>
            <div className="bg-arctic-surface dark:bg-molten-surface p-5 rounded-lg border border-outline-variant/50 dark:border-[#2A345E]/50 shadow-sm hover:shadow-md transition-all duration-300">
              <div className="flex items-center justify-between mb-4">
                <span className="material-symbols-outlined text-primary dark:text-molten-primary">bolt</span>
                <span className="text-arctic-text-muted dark:text-molten-text-muted font-bold text-label-sm">Steady</span>
              </div>
              <p className="text-arctic-text-muted dark:text-molten-text-muted font-label-sm uppercase tracking-wider mb-1">Concurrency</p>
              <p className="font-headline-md text-headline-md tabular-nums">480/500</p>
            </div>
          </div>

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
              {campaigns.map((camp) => {
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
                                onClick={(e) => { e.stopPropagation(); handleToggleCampaign(camp.id, 'running'); }}
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
                          <h3 className="font-headline-sm text-headline-sm mb-2">{camp.name}</h3>
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
                        <h3 className="font-headline-sm text-headline-sm mb-2">{camp.name}</h3>
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
                          onClick={(e) => { e.stopPropagation(); handleToggleCampaign(camp.id, 'paused'); }}
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
                        <h3 className="font-headline-sm text-headline-sm mb-2">{camp.name}</h3>
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
              })}
            </div>
          )}
        </div>
      </main>

      {/* TODO: Campaign Creation Wizard Modal (Phase 2/3 campaign creation)
      <div className={`fixed inset-0 z-[100] ${isWizardOpen ? 'flex' : 'hidden'} items-center justify-center`}>
        <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setIsWizardOpen(false)}></div>
        
        <div className="absolute bottom-0 left-0 right-0 md:relative md:bottom-auto max-w-2xl w-full mx-auto bg-arctic-surface dark:bg-molten-surface rounded-t-2xl md:rounded-2xl shadow-2xl overflow-hidden modal-transition transform scale-100 opacity-100 flex flex-col max-h-[90vh]">
          
          <div className="p-6 border-b border-outline-variant dark:border-[#2A345E] flex justify-between items-center">
            <h2 className="font-headline-md text-headline-md">Create New Campaign</h2>
            <button className="p-2 hover:bg-surface-container rounded-full cursor-pointer animate-pulse" onClick={() => setIsWizardOpen(false)}>
              <span className="material-symbols-outlined">close</span>
            </button>
          </div>

          <div className="flex border-b border-outline-variant dark:border-[#2A345E]">
            <div className={`flex-1 p-4 text-center border-b-2 transition-colors ${wizardStep === 1 ? 'border-primary dark:border-molten-primary text-primary dark:text-molten-primary font-bold' : 'border-transparent text-arctic-text-muted'}`}>
              <span className="font-label-md">1. Bot Selection</span>
            </div>
            <div className={`flex-1 p-4 text-center border-b-2 transition-colors ${wizardStep === 2 ? 'border-primary dark:border-molten-primary text-primary dark:text-molten-primary font-bold' : 'border-transparent text-arctic-text-muted'}`}>
              <span className="font-label-md">2. Budget</span>
            </div>
            <div className={`flex-1 p-4 text-center border-b-2 transition-colors ${wizardStep === 3 ? 'border-primary dark:border-molten-primary text-primary dark:text-molten-primary font-bold' : 'border-transparent text-arctic-text-muted'}`}>
              <span className="font-label-md">3. Concurrency</span>
            </div>
          </div>

          <div className="p-6 space-y-5 overflow-y-auto flex-grow">
            {wizardStep === 1 && (
              <div className="space-y-5 animate-fade-in">
                <div className="space-y-4">
                  <label className="block font-label-md text-label-md text-on-surface dark:text-molten-text">Choose AI Persona</label>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <button
                      onClick={() => setNewCampaign({ ...newCampaign, bot_config_id: 'sales-specialist-uuid' })}
                      className={`flex items-center gap-4 p-4 rounded-xl border-2 text-left transition-all cursor-pointer ${
                        newCampaign.bot_config_id === 'sales-specialist-uuid'
                          ? 'border-primary dark:border-molten-primary bg-primary/5 dark:bg-molten-primary/5'
                          : 'border-outline-variant dark:border-[#2A345E] hover:border-primary/50'
                      }`}
                    >
                      <div className={`w-12 h-12 rounded-full flex items-center justify-center ${
                        newCampaign.bot_config_id === 'sales-specialist-uuid' ? 'bg-primary/20 text-primary dark:text-molten-primary' : 'bg-surface-container text-outline'
                      }`}>
                        <span className="material-symbols-outlined">smart_toy</span>
                      </div>
                      <div>
                        <p className="font-bold text-on-surface dark:text-molten-text">Sales Specialist</p>
                        <p className="text-xs text-arctic-text-muted dark:text-molten-text-muted">High energy, persuasive</p>
                      </div>
                    </button>
                    
                    <button
                      onClick={() => setNewCampaign({ ...newCampaign, bot_config_id: 'support-guide-uuid' })}
                      className={`flex items-center gap-4 p-4 rounded-xl border-2 text-left transition-all cursor-pointer ${
                        newCampaign.bot_config_id === 'support-guide-uuid'
                          ? 'border-primary dark:border-molten-primary bg-primary/5 dark:bg-molten-primary/5'
                          : 'border-outline-variant dark:border-[#2A345E] hover:border-primary/50'
                      }`}
                    >
                      <div className={`w-12 h-12 rounded-full flex items-center justify-center ${
                        newCampaign.bot_config_id === 'support-guide-uuid' ? 'bg-primary/20 text-primary dark:text-molten-primary' : 'bg-surface-container text-outline'
                      }`}>
                        <span className="material-symbols-outlined">support_agent</span>
                      </div>
                      <div>
                        <p className="font-bold text-on-surface dark:text-molten-text">Support Guide</p>
                        <p className="text-xs text-arctic-text-muted dark:text-molten-text-muted">Calm, helpful, patient</p>
                      </div>
                    </button>
                  </div>
                </div>

                <div className="space-y-4">
                  <label className="block font-label-md text-label-md text-on-surface dark:text-molten-text">Campaign Objective / Name</label>
                  <input
                    className="w-full bg-surface-container-low dark:bg-surface-variant/10 border border-outline-variant dark:border-[#2A345E] rounded-lg p-3 outline-none focus:border-primary dark:focus:border-molten-primary text-on-surface dark:text-molten-text transition-colors"
                    placeholder="e.g. Q4 Real Estate Outreach"
                    type="text"
                    value={newCampaign.name}
                    onChange={(e) => setNewCampaign({ ...newCampaign, name: e.target.value })}
                  />
                </div>
              </div>
            )}

            {wizardStep === 2 && (
              <div className="space-y-6 animate-fade-in">
                <div className="space-y-4">
                  <label className="block font-label-md text-label-md text-on-surface dark:text-molten-text">Allocate Budget (Credits)</label>
                  <p className="text-xs text-arctic-text-muted mb-2">Available Account Balance: {formatINR(balance)}</p>
                  <div className="relative flex items-center">
                    <input
                      className="w-full bg-surface-container-low dark:bg-surface-variant/10 border border-outline-variant dark:border-[#2A345E] rounded-lg p-4 pl-12 outline-none focus:border-primary dark:focus:border-molten-primary text-on-surface dark:text-molten-text transition-colors text-xl font-bold tabular-nums"
                      type="number"
                      min="100"
                      step="100"
                      value={newCampaign.budget_credits}
                      onChange={(e) => setNewCampaign({ ...newCampaign, budget_credits: Number(e.target.value) })}
                    />
                    <span className="absolute left-4 font-bold text-lg text-primary dark:text-molten-primary">₹</span>
                  </div>
                  <p className="text-xs text-arctic-text-muted">Note: Calls charge credits per minute based on the selected bot config pricing model.</p>
                </div>
              </div>
            )}

            {wizardStep === 3 && (
              <div className="space-y-6 animate-fade-in">
                <div className="space-y-4">
                  <label className="block font-label-md text-label-md text-on-surface dark:text-molten-text">Max Concurrent Calls (Channels)</label>
                  <div className="flex items-center gap-4">
                    <input
                      type="range"
                      min="1"
                      max={maxConcurrency}
                      className="w-full h-2 bg-surface-container rounded-lg appearance-none cursor-pointer accent-primary dark:accent-molten-primary"
                      value={newCampaign.max_concurrent_calls}
                      onChange={(e) => setNewCampaign({ ...newCampaign, max_concurrent_calls: Number(e.target.value) })}
                    />
                    <span className="text-xl font-bold border border-outline-variant rounded-lg px-4 py-2 bg-surface-container-low dark:bg-surface-variant/10 tabular-nums">
                      {newCampaign.max_concurrent_calls}
                    </span>
                  </div>
                  <p className="text-xs text-arctic-text-muted">Allocating more concurrent calls allows dialing numbers in parallel, accelerating campaign speed. Maximum channel concurrency limit: {maxConcurrency}.</p>
                </div>
              </div>
            )}
          </div>

          <div className="p-6 bg-surface-container-low dark:bg-surface-variant/10 flex justify-between items-center border-t border-outline-variant dark:border-[#2A345E]">
            <div>
              {wizardStep > 1 && (
                <button
                  onClick={() => setWizardStep(prev => prev - 1)}
                  className="px-6 py-2 font-medium hover:bg-surface-container rounded-lg transition-colors cursor-pointer text-on-surface dark:text-molten-text border border-outline-variant"
                >
                  Back
                </button>
              )}
            </div>
            <div className="flex gap-4">
              <Button
                variant="outline"
                onClick={() => { setIsWizardOpen(false); resetWizard(); }}
                className="!px-6 !py-2"
              >
                Cancel
              </Button>
              
              {wizardStep < 3 ? (
                <Button
                  onClick={() => {
                    if (wizardStep === 1 && !newCampaign.name.trim()) {
                      alert('Please specify a campaign objective name.');
                      return;
                    }
                    setWizardStep(prev => prev + 1);
                  }}
                  className="!px-8 !py-2"
                >
                  Next Step
                </Button>
              ) : (
                <Button
                  onClick={handleCreateCampaign}
                  className="!px-8 !py-2"
                >
                  Create Campaign
                </Button>
              )}
            </div>
          </div>

        </div>
      </div>
      */}

      {/* Mobile Navigation */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-arctic-surface dark:bg-molten-surface border-t border-outline-variant dark:border-[#2A345E] flex justify-around p-3 z-50 transition-colors duration-500">
        <a className="flex flex-col items-center text-primary dark:text-molten-primary" href="#">
          <span className="material-symbols-outlined">dashboard</span>
          <span className="text-[10px] font-bold">Home</span>
        </a>
        <a className="flex flex-col items-center text-arctic-text-muted dark:text-molten-text-muted" href="#">
          <span className="material-symbols-outlined">campaign</span>
          <span className="text-[10px]">Campaigns</span>
        </a>
        {/* TODO: Phase 2/3 mobile campaign creation
        <button onClick={() => setIsWizardOpen(true)} className="-mt-8 bg-primary w-14 h-14 rounded-full flex items-center justify-center text-white shadow-lg border-4 border-arctic-bg dark:border-molten-bg cursor-pointer">
          <span className="material-symbols-outlined">add</span>
        </button>
        */}
        {/* TODO: Phase 3 analytics
        <a className="flex flex-col items-center text-arctic-text-muted dark:text-molten-text-muted" href="#">
          <span className="material-symbols-outlined">analytics</span>
          <span className="text-[10px]">Stats</span>
        </a>
        */}
        {/* TODO: Mobile settings
        <a className="flex flex-col items-center text-arctic-text-muted dark:text-molten-text-muted" href="#">
          <span className="material-symbols-outlined">settings</span>
          <span className="text-[10px]">Settings</span>
        </a>
        */}
      </nav>

    </div>
  );
};

export default Dashboard;
