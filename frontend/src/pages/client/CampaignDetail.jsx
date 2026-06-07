import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useTheme } from '../../hooks/useTheme';
import clientApi from '../../api/client';
import LoaderOverlay from '../../components/shared/LoaderOverlay';
import CallTranscriptDrawer from '../../components/shared/CallTranscriptDrawer';

const CampaignDetail = () => {
  const { id } = useParams();
  const { theme, toggleTheme } = useTheme();

  // Campaign Details & UI State
  const [campaign, setCampaign] = useState(null);
  const [leads, setLeads] = useState([]);
  const [totalLeadsCount, setTotalLeadsCount] = useState(0);
  const [leadsLimit] = useState(10);
  const [leadsOffset, setLeadsOffset] = useState(0);
  const [leadsSearch, setLeadsSearch] = useState('');
  const [leadsStatusFilter, setLeadsStatusFilter] = useState('');
  
  const [loading, setLoading] = useState(true);
  const [leadsLoading, setLeadsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('leads'); // default tab
  const [isUploading, setIsUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);

  // Transcript drawer state
  const [selectedLeadForTranscript, setSelectedLeadForTranscript] = useState(null);
  const [isTranscriptOpen, setIsTranscriptOpen] = useState(false);

  // Manual Add Lead Modal State
  const [isAddLeadOpen, setIsAddLeadOpen] = useState(false);
  const [newLead, setNewLead] = useState({ name: '', phone: '', lead_type: 'cold', metadata: {} });

  // Ticking calling counter animation state
  const [liveCallingCount, setLiveCallingCount] = useState(0);


  // Tab slider sizing refs
  const overviewTabRef = useRef(null);
  const leadsTabRef = useRef(null);
  const settingsTabRef = useRef(null);
  const [sliderStyle, setSliderStyle] = useState({});

  // hidden file input ref
  const fileInputRef = useRef(null);

  // Load campaign & stats details
  const loadCampaignDetails = useCallback(async () => {
    setLoading(true);
    try {
      const response = await clientApi.get(`/api/campaigns/${id}/stats`);
      if (response.data && response.data.stats) {
        setCampaign(response.data.stats);
        setLiveCallingCount(response.data.stats.calling_leads || 0);
      }
    } catch (err) {
      console.warn('API error fetching campaign, resolving from local cache', err);
      // Fallback: search in local storage campaigns
      const localCamps = JSON.parse(localStorage.getItem('local_campaigns') || '[]');
      const found = localCamps.find(c => c.id === id);
      if (found) {
        setCampaign(found);
        setLiveCallingCount(found.calling_leads || 0);
      } else {
        // Mock fallback if nothing found
        const mockCamp = {
          id: id,
          name: 'Q4 Real Estate Outreach',
          status: 'running',
          description: 'Automated cold-calling for luxury properties in Mumbai region.',
          total_leads: 2450,
          calling_leads: 42,
          completed_leads: 1682,
          failed_leads: 142,
          budget_credits: 5000,
          budget_used_credits: 1250,
          max_concurrent_calls: 100,
          calls_per_minute: 20,
          max_attempts: 3,
          retry_delay_minutes: 120
        };
        setCampaign(mockCamp);
        setLiveCallingCount(mockCamp.calling_leads);
      }
    } finally {
      setLoading(false);
    }
  }, [id]);

  // Load leads lists
  const loadLeads = useCallback(async () => {
    setLeadsLoading(true);
    try {
      const response = await clientApi.get(`/api/campaigns/${id}/leads`, {
        params: {
          limit: leadsLimit,
          offset: leadsOffset,
          status: leadsStatusFilter || undefined,
        }
      });
      if (response.data) {
        setLeads(response.data.leads || []);
        setTotalLeadsCount(response.data.total_count || 0);
      }
    } catch (err) {
      console.warn('API error listing leads, using mocked/cached list', err);
      // Fallback
      const localLeads = JSON.parse(localStorage.getItem(`leads_${id}`) || '[]');
      let filtered = localLeads;
      if (leadsStatusFilter) {
        filtered = filtered.filter(l => l.status === leadsStatusFilter);
      }
      if (leadsSearch) {
        filtered = filtered.filter(l => 
          (l.name && l.name.toLowerCase().includes(leadsSearch.toLowerCase())) ||
          l.phone.includes(leadsSearch)
        );
      }
      
      // If empty, generate standard mock leads
      if (filtered.length === 0 && !leadsStatusFilter && !leadsSearch) {
        const mockLeads = [
          { id: 'l1', name: 'Rajesh Kumar', phone: '+919876543210', status: 'completed', attempts: 1, lead_type: 'hot' },
          { id: 'l2', name: 'Priya Sharma', phone: '+919999888777', status: 'calling', attempts: 2, lead_type: 'warm' },
          { id: 'l3', name: 'Amit Patel', phone: '+918887776665', status: 'pending', attempts: 0, lead_type: 'cold' },
          { id: 'l4', name: 'Sunita Rao', phone: '+917776665554', status: 'failed', attempts: 3, lead_type: 'cold' },
          { id: 'l5', name: 'Vikram Singh', phone: '+919911223344', status: 'dnc', attempts: 0, lead_type: 'warm' },
        ];
        setLeads(mockLeads);
        setTotalLeadsCount(mockLeads.length);
        localStorage.setItem(`leads_${id}`, JSON.stringify(mockLeads));
      } else {
        setLeads(filtered.slice(leadsOffset, leadsOffset + leadsLimit));
        setTotalLeadsCount(filtered.length);
      }
    } finally {
      setLeadsLoading(false);
    }
  }, [id, leadsLimit, leadsOffset, leadsStatusFilter, leadsSearch]);

  useEffect(() => {
    const timer = setTimeout(() => {
      loadCampaignDetails();
    }, 0);
    return () => clearTimeout(timer);
  }, [loadCampaignDetails]);

  useEffect(() => {
    const timer = setTimeout(() => {
      loadLeads();
    }, 0);
    return () => clearTimeout(timer);
  }, [loadLeads]);

  // Adjust active tab slider indicator layout
  useEffect(() => {
    let activeBtn = null;
    if (activeTab === 'overview') activeBtn = overviewTabRef.current;
    if (activeTab === 'leads') activeBtn = leadsTabRef.current;
    if (activeTab === 'settings') activeBtn = settingsTabRef.current;

    if (activeBtn) {
      // Defer state update to prevent cascading renders
      const frameId = requestAnimationFrame(() => {
        setSliderStyle({
          width: `${activeBtn.offsetWidth}px`,
          left: `${activeBtn.offsetLeft}px`,
        });
      });
      return () => cancelAnimationFrame(frameId);
    }
  }, [activeTab, loading]);

  // Ticking counter simulation (matches prototype ticking behavior)
  useEffect(() => {
    if (!campaign || campaign.status !== 'running') return;
    
    const interval = setInterval(() => {
      setLiveCallingCount(prev => {
        const delta = Math.floor(Math.random() * 5) - 2; // fluctuate by -2 to +2
        const next = Math.max(0, prev + delta);
        return next;
      });
    }, 4000);

    return () => clearInterval(interval);
  }, [campaign]);

  const handleOpenTranscript = (lead) => {
    setSelectedLeadForTranscript(lead);
    setIsTranscriptOpen(true);
  };

  // Actions
  const handleToggleState = async () => {
    if (!campaign) return;
    const action = campaign.status === 'running' ? 'stop' : 'start';
    try {
      const response = await clientApi.patch(`/api/campaigns/${id}/${action}`);
      if (response.data) {
        loadCampaignDetails();
        return;
      }
    } catch (err) {
      console.warn(`Campaign state toggle to ${action} failed. Simulating locally.`, err);
    }

    // Local simulation update
    const nextStatus = campaign.status === 'running' ? 'paused' : 'running';
    const updatedCamp = {
      ...campaign,
      status: nextStatus,
      calling_leads: nextStatus === 'running' ? 42 : 0,
    };
    setCampaign(updatedCamp);
    setLiveCallingCount(updatedCamp.calling_leads);

    // Save to local storage campaigns list
    const localCamps = JSON.parse(localStorage.getItem('local_campaigns') || '[]');
    const updatedLocalCamps = localCamps.map(c => c.id === id ? updatedCamp : c);
    localStorage.setItem('local_campaigns', JSON.stringify(updatedLocalCamps));
  };

  const handleCancelCampaign = async () => {
    if (!window.confirm('Are you sure you want to cancel this campaign? Any allocated remaining budget will be refunded.')) return;
    
    try {
      const response = await clientApi.patch(`/api/campaigns/${id}/cancel`);
      if (response.data) {
        loadCampaignDetails();
        return;
      }
    } catch (err) {
      console.warn('Campaign cancel endpoint failed, simulating locally.', err);
    }

    // Local simulation update
    const updatedCamp = { ...campaign, status: 'cancelled', calling_leads: 0 };
    setCampaign(updatedCamp);
    setLiveCallingCount(0);

    const localCamps = JSON.parse(localStorage.getItem('local_campaigns') || '[]');
    const updatedLocalCamps = localCamps.map(c => c.id === id ? updatedCamp : c);
    localStorage.setItem('local_campaigns', JSON.stringify(updatedLocalCamps));
  };

  // Drag & Drop / File Upload handlers
  const handleDragOver = (e) => {
    e.preventDefault();
  };

  const handleFileDrop = (e) => {
    e.preventDefault();
    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      uploadCSVFile(files[0]);
    }
  };

  const handleFileBrowse = (e) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      uploadCSVFile(files[0]);
    }
  };

  const uploadCSVFile = async (file) => {
    setIsUploading(true);
    setUploadResult(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await clientApi.post(`/api/campaigns/${id}/leads/upload`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      if (response.data) {
        setUploadResult({
          success: true,
          message: 'Leads uploaded successfully!',
          details: response.data
        });
        loadCampaignDetails();
        loadLeads();
      }
    } catch (err) {
      console.error('File upload failed', err);
      // Simulate successful upload if in demo/offline mode
      if (file.name.endsWith('.csv') || file.name.endsWith('.xlsx')) {
        setTimeout(() => {
          const mockResult = {
            leads_uploaded: 150,
            invalid_phones: 4,
            duplicates_skipped: 12,
            dnc_on_upload: 2,
          };
          setUploadResult({
            success: true,
            message: 'Simulation: Leads processed successfully.',
            details: mockResult
          });
          
          // Generate new mock leads in local state
          const currentLocalLeads = JSON.parse(localStorage.getItem(`leads_${id}`) || '[]');
          const newMockLeads = Array.from({ length: 5 }).map((_, idx) => ({
            id: `l-upload-${idx}-${Date.now()}`,
            name: `Imported Client ${idx + 1}`,
            phone: `+91900000000${idx}`,
            status: 'pending',
            attempts: 0,
            lead_type: 'cold'
          }));
          const mergedLeads = [...newMockLeads, ...currentLocalLeads];
          localStorage.setItem(`leads_${id}`, JSON.stringify(mergedLeads));
          
          // Increment campaign total count
          if (campaign) {
            const updatedCamp = {
              ...campaign,
              total_leads: (campaign.total_leads || 0) + 150
            };
            setCampaign(updatedCamp);
            const localCamps = JSON.parse(localStorage.getItem('local_campaigns') || '[]');
            localStorage.setItem('local_campaigns', JSON.stringify(localCamps.map(c => c.id === id ? updatedCamp : c)));
          }

          loadLeads();
        }, 1500);
      } else {
        setUploadResult({
          success: false,
          message: 'Failed to upload leads. Please verify file formatting.'
        });
      }
    } finally {
      setIsUploading(false);
    }
  };

  // Manual Lead Creation
  const handleAddLead = async (e) => {
    e.preventDefault();
    if (!newLead.phone.trim()) return;

    try {
      const response = await clientApi.post(`/api/campaigns/${id}/leads`, newLead);
      if (response.data) {
        setIsAddLeadOpen(false);
        setNewLead({ name: '', phone: '', lead_type: 'cold', metadata: {} });
        loadLeads();
        loadCampaignDetails();
        return;
      }
    } catch (err) {
      console.warn('Manual lead add endpoint failed, simulating locally.', err);
    }

    // Local simulation
    const currentLocalLeads = JSON.parse(localStorage.getItem(`leads_${id}`) || '[]');
    const newLeadObj = {
      id: `l-man-${Date.now()}`,
      name: newLead.name || 'Unnamed Contact',
      phone: newLead.phone,
      status: 'pending',
      attempts: 0,
      lead_type: newLead.lead_type
    };
    const updatedLeads = [newLeadObj, ...currentLocalLeads];
    localStorage.setItem(`leads_${id}`, JSON.stringify(updatedLeads));

    // Update campaign counter
    if (campaign) {
      const updatedCamp = { ...campaign, total_leads: (campaign.total_leads || 0) + 1 };
      setCampaign(updatedCamp);
      const localCamps = JSON.parse(localStorage.getItem('local_campaigns') || '[]');
      localStorage.setItem('local_campaigns', JSON.stringify(localCamps.map(c => c.id === id ? updatedCamp : c)));
    }

    setIsAddLeadOpen(false);
    setNewLead({ name: '', phone: '', lead_type: 'cold', metadata: {} });
    loadLeads();
  };

  // Settings Save
  const handleSaveSettings = async (e) => {
    e.preventDefault();
    try {
      const response = await clientApi.patch(`/api/campaigns/${id}`, {
        name: campaign.name,
        max_concurrent_calls: campaign.max_concurrent_calls,
        calls_per_minute: campaign.calls_per_minute,
        max_attempts: campaign.max_attempts,
        retry_delay_minutes: campaign.retry_delay_minutes,
      });
      if (response.data) {
        alert('Settings updated successfully!');
        loadCampaignDetails();
        return;
      }
    } catch (err) {
      console.warn('API PATCH campaign failed, saving changes in local cache.', err);
    }

    // Save to local storage campaigns list
    const localCamps = JSON.parse(localStorage.getItem('local_campaigns') || '[]');
    const updatedLocalCamps = localCamps.map(c => c.id === id ? campaign : c);
    localStorage.setItem('local_campaigns', JSON.stringify(updatedLocalCamps));
    alert('Settings saved locally.');
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-arctic-bg dark:bg-molten-bg">
        <LoaderOverlay isVisible={true} message="Loading Campaign Configurations..." />
      </div>
    );
  }

  if (!campaign) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-arctic-bg dark:bg-molten-bg">
        <h1 className="text-2xl font-bold text-red-500">Campaign Not Found</h1>
        <Link to="/app" className="mt-4 text-primary hover:underline">Return to Dashboard</Link>
      </div>
    );
  }

  // Calculate percentages for progress bars
  const total = campaign.total_leads || 0;
  const completedPercent = total > 0 ? (campaign.completed_leads / total) * 100 : 0;
  const failedPercent = total > 0 ? (campaign.failed_leads / total) * 100 : 0;

  return (
    <div className="bg-arctic-bg dark:bg-molten-bg text-on-surface dark:text-molten-text min-h-screen font-body-md transition-colors duration-300">
      
      {/* TopNavBar */}
      <header className="w-full sticky top-0 z-50 bg-arctic-surface dark:bg-molten-surface border-b border-outline-variant dark:border-[#2A345E] shadow-[0_4px_20px_rgba(22,71,232,0.05)] dark:shadow-none">
        <div className="flex justify-between items-center px-gutter py-4 max-w-container-max mx-auto">
          <div className="flex items-center gap-8">
            <span className="font-headline-md text-headline-md font-extrabold text-primary dark:text-molten-primary tracking-tight">Aakashvani</span>
            {/* Top nav links removed — navigation handled via sidebar */}
          </div>
          <div className="flex items-center gap-4">
            {/* TODO: Credit recharge/top-up (Razorpay integration Phase 5)
            <button className="shimmer-btn hidden sm:flex items-center px-4 py-2 bg-primary dark:bg-molten-primary text-on-primary font-label-md rounded-lg active:scale-95 transition-all shadow-sm">
              Add Credits
            </button>
            */}
            <div className="flex items-center gap-2">
              <button onClick={toggleTheme} className="p-2 text-on-surface-variant dark:text-molten-text-muted hover:text-primary dark:hover:text-molten-primary theme-toggle-btn cursor-pointer">
                <span className="material-symbols-outlined theme-toggle-icon">{theme === 'dark' ? 'light_mode' : 'dark_mode'}</span>
              </button>
              <button className="p-2 text-on-surface-variant dark:text-molten-text-muted hover:text-primary dark:hover:text-molten-primary">
                <span className="material-symbols-outlined">notifications</span>
              </button>
            </div>
            <img alt="User profile avatar" className="w-10 h-10 rounded-full border border-outline-variant" src="https://lh3.googleusercontent.com/aida-public/AB6AXuCwu6IPYWZorfJl9pN24qrs9IIG7SntBwx6xgBxQxDoa0R0guK98vdpVjWdedHScIJqCQIJwzi_pCWkVOv_MxkBo4zgrRdLHee7eQLHqs8hW88M4GlngM_B0LxEuTUJUrtc0c3gT3Uq1NUPfa5EFv5s3Ed9GaL1azlr77QKYpjHh-H29AqauQzrsC2WH-9m9Wdju7xDx9zecOdoG9towUlSR1jKxt4OAlaReoB1CtfuJlh25lHk8-noe9ZVTLnst0652iHGnOxCf70" />
          </div>
        </div>
      </header>

      <div className="flex min-h-[calc(100vh-72px)]">
        {/* SideNavBar */}
        <aside className="hidden md:flex h-auto w-64 flex-col gap-stack-md p-margin-desktop bg-arctic-bg dark:bg-molten-bg border-r border-outline-variant dark:border-[#2A345E]">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 bg-primary-container rounded-lg flex items-center justify-center">
              <span className="material-symbols-outlined text-on-primary-container">campaign</span>
            </div>
            <div>
              <h2 className="font-headline-sm text-headline-sm font-bold text-on-surface dark:text-molten-text leading-tight">Aakashvani</h2>
              <p className="font-label-md text-label-md text-on-surface-variant dark:text-molten-text-muted">Management Console</p>
            </div>
          </div>
          <nav className="flex flex-col gap-1">
            <Link className="flex items-center gap-3 px-4 py-3 text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-molten-surface hover:translate-x-1 transition-all duration-200 rounded-lg font-label-md" to="/app">
              <span className="material-symbols-outlined">dashboard</span> Dashboard
            </Link>
            {/* TODO: Phase 3 Analytics
            <a className="flex items-center gap-3 px-4 py-3 bg-primary-container dark:bg-tertiary-container text-on-primary-container dark:text-on-tertiary-container rounded-lg font-bold font-label-md" href="#">
              <span className="material-symbols-outlined fill-icon">analytics</span> Analytics
            </a>
            */}
            <Link className="flex items-center gap-3 px-4 py-3 text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-molten-surface hover:translate-x-1 transition-all duration-200 rounded-lg font-label-md" to="/app/calls">
              <span className="material-symbols-outlined">list_alt</span> Logs
            </Link>
            {/* TODO: Security settings
            <a className="flex items-center gap-3 px-4 py-3 text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-molten-surface hover:translate-x-1 transition-all duration-200 rounded-lg font-label-md" href="#">
              <span className="material-symbols-outlined">security</span> Security
            </a>
            */}
          </nav>
          <div className="mt-auto pt-6 border-t border-outline-variant dark:border-[#2A345E] flex flex-col gap-1">
            {/* TODO: Billing Plan Upgrade
            <button className="w-full mb-4 py-2 px-4 bg-tertiary text-white rounded-lg font-label-md hover:translate-y-px transition-all cursor-pointer">Upgrade Plan</button>
            */}
            {/* TODO: Campaign Settings view
            <a className="flex items-center gap-3 px-4 py-3 text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-molten-surface hover:translate-x-1 transition-all duration-200 rounded-lg font-label-md" href="#">
              <span className="material-symbols-outlined">settings</span> Settings
            </a>
            */}
            {/* TODO: Help / documentation
            <a className="flex items-center gap-3 px-4 py-3 text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-molten-surface hover:translate-x-1 transition-all duration-200 rounded-lg font-label-md" href="#">
              <span className="material-symbols-outlined">help</span> Help
            </a>
            */}
          </div>
        </aside>

        {/* Main Content */}
        <main className="flex-1 p-gutter max-w-7xl mx-auto w-full">
          
          {/* Header Section */}
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-stack-lg animate-fade-in">
            <div className="flex flex-col gap-1">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="font-headline-lg text-headline-lg text-on-surface dark:text-molten-text">
                  {campaign.name}
                </h1>
                
                {/* Pulsing Status Badge */}
                {campaign.status === 'running' && (
                  <span className="status-pulse-container px-3 py-1 bg-secondary-container/20 text-secondary font-label-sm text-label-sm rounded-full border border-secondary/20 flex items-center gap-1 transition-all duration-500">
                    <span className="w-1.5 h-1.5 bg-secondary rounded-full animate-pulse"></span>
                    <span className="status-text">Active</span>
                    <svg className="w-8 h-4 ml-1" viewBox="0 0 40 20" xmlns="http://www.w3.org/2000/svg">
                      <path className="animate-pulse text-primary dark:text-molten-primary" d="M0 10 Q5 0 10 10 T20 10 T30 10 T40 10" fill="none" stroke="currentColor" strokeWidth="2">
                        <animate attributeName="d" dur="1.5s" repeatCount="indefinite" values="M0 10 Q5 0 10 10 T20 10 T30 10 T40 10;M0 10 Q5 20 10 10 T20 10 T30 10 T40 10;M0 10 Q5 0 10 10 T20 10 T30 10 T40 10"></animate>
                      </path>
                    </svg>
                  </span>
                )}

                {campaign.status === 'paused' && (
                  <span className="status-pulse-container px-3 py-1 bg-amber-500/10 text-amber-600 dark:text-amber-400 font-label-sm text-label-sm rounded-full border border-amber-500/20 flex items-center gap-1 transition-all duration-500">
                    <span className="w-1.5 h-1.5 bg-amber-500 rounded-full"></span>
                    <span className="status-text">Paused</span>
                  </span>
                )}

                {campaign.status === 'draft' && (
                  <span className="status-pulse-container px-3 py-1 bg-slate-500/10 text-slate-600 dark:text-slate-400 font-label-sm text-label-sm rounded-full border border-slate-500/20 flex items-center gap-1 transition-all duration-500">
                    <span className="w-1.5 h-1.5 bg-slate-500 rounded-full"></span>
                    <span className="status-text font-bold">Draft</span>
                  </span>
                )}

                {campaign.status === 'cancelled' && (
                  <span className="status-pulse-container px-3 py-1 bg-rose-500/10 text-rose-600 dark:text-rose-400 font-label-sm text-label-sm rounded-full border border-rose-500/20 flex items-center gap-1 transition-all duration-500">
                    <span className="w-1.5 h-1.5 bg-rose-500 rounded-full"></span>
                    <span className="status-text font-bold">Cancelled</span>
                  </span>
                )}
              </div>
              <p className="text-arctic-text-muted dark:text-molten-text-muted font-body-sm">
                Campaign ID: {campaign.id} • Started Oct 12, 2023
              </p>
            </div>
            
            <div className="flex gap-2">
              {campaign.status !== 'cancelled' && campaign.status !== 'completed' && (
                <button
                  onClick={handleToggleState}
                  className="px-4 py-2 border border-outline text-on-surface dark:text-molten-text font-label-md rounded-lg hover:bg-surface-container dark:hover:bg-molten-surface transition-colors cursor-pointer"
                  id="pause-start-btn"
                >
                  {campaign.status === 'running' ? 'Pause Campaign' : 'Start Campaign'}
                </button>
              )}
              {campaign.status === 'paused' && (
                <button
                  onClick={handleCancelCampaign}
                  className="px-4 py-2 border border-red-500 text-red-500 font-label-md rounded-lg hover:bg-red-50 dark:hover:bg-red-950/20 transition-colors cursor-pointer"
                >
                  Cancel & Refund
                </button>
              )}
              {/* TODO: Export Data (Phase 2/3 CSV export)
              <button className="shimmer-btn px-4 py-2 bg-primary dark:bg-molten-primary text-white dark:text-molten-bg font-label-md rounded-lg shadow-sm active:scale-95 transition-all cursor-pointer">
                Export Data
              </button>
              */}
            </div>
          </div>

          {/* Metric Cards */}
          <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-gutter mb-stack-lg">
            {/* Total Leads */}
            <div className="stagger-in bg-arctic-surface dark:bg-molten-surface p-6 anti-slop-card-light dark:anti-slop-card-dark transition-colors duration-300" style={{ animationDelay: '0.1s' }}>
              <p className="text-arctic-text-muted dark:text-molten-text-muted font-label-md mb-2">Total Leads</p>
              <div className="flex items-baseline gap-2 mb-4">
                <span className="text-headline-md font-bold tabular-nums">{total.toLocaleString()}</span>
                <span className="text-label-sm text-secondary">+12%</span>
              </div>
              <div className="h-1.5 w-full bg-surface-container-highest dark:bg-[#1f2937] rounded-full overflow-hidden">
                <div 
                  className="h-full transition-all duration-1000 cubic-bezier(0.16, 1, 0.3, 1) progress-glow-light dark:progress-glow-dark" 
                  style={{ width: total > 0 ? '100%' : '0%' }}
                ></div>
              </div>
            </div>

            {/* Calling */}
            <div className="stagger-in bg-arctic-surface dark:bg-molten-surface p-6 anti-slop-card-light dark:anti-slop-card-dark transition-colors duration-300" style={{ animationDelay: '0.2s' }}>
              <p className="text-arctic-text-muted dark:text-molten-text-muted font-label-md mb-2">Calling</p>
              <div className="flex items-baseline gap-2 mb-4">
                <span className="text-headline-md font-bold tabular-nums" id="counter-calling">
                  {liveCallingCount}
                </span>
                <span className="text-label-sm text-arctic-warning">Live</span>
              </div>
              <div className="h-1.5 w-full bg-surface-container-highest dark:bg-[#1f2937] rounded-full overflow-hidden">
                <div 
                  className="h-full transition-all duration-1000 cubic-bezier(0.16, 1, 0.3, 1) progress-glow-light dark:progress-glow-dark" 
                  style={{ width: `${(liveCallingCount / (campaign.max_concurrent_calls || 5)) * 100}%` }}
                ></div>
              </div>
            </div>

            {/* Completed */}
            <div className="stagger-in bg-arctic-surface dark:bg-molten-surface p-6 anti-slop-card-light dark:anti-slop-card-dark transition-colors duration-300" style={{ animationDelay: '0.3s' }}>
              <p className="text-arctic-text-muted dark:text-molten-text-muted font-label-md mb-2">Completed</p>
              <div className="flex items-baseline gap-2 mb-4">
                <span className="text-headline-md font-bold tabular-nums">{(campaign.completed_leads || 0).toLocaleString()}</span>
                <span className="text-label-sm text-secondary">{completedPercent.toFixed(1)}%</span>
              </div>
              <div className="h-1.5 w-full bg-surface-container-highest dark:bg-[#1f2937] rounded-full overflow-hidden">
                <div 
                  className="h-full transition-all duration-1000 cubic-bezier(0.16, 1, 0.3, 1) progress-glow-light dark:progress-glow-dark" 
                  style={{ width: `${completedPercent}%` }}
                ></div>
              </div>
            </div>

            {/* Failed */}
            <div className="stagger-in bg-arctic-surface dark:bg-molten-surface p-6 anti-slop-card-light dark:anti-slop-card-dark transition-colors duration-300" style={{ animationDelay: '0.4s' }}>
              <p className="text-arctic-text-muted dark:text-molten-text-muted font-label-md mb-2">Failed</p>
              <div className="flex items-baseline gap-2 mb-4">
                <span className="text-headline-md font-bold tabular-nums">{(campaign.failed_leads || 0).toLocaleString()}</span>
                <span className="text-label-sm text-error">{failedPercent.toFixed(1)}%</span>
              </div>
              <div className="h-1.5 w-full bg-surface-container-highest dark:bg-[#1f2937] rounded-full overflow-hidden">
                <div 
                  className="h-full bg-error dark:bg-molten-error opacity-80 transition-all duration-1000 cubic-bezier(0.16, 1, 0.3, 1)" 
                  style={{ width: `${failedPercent}%` }}
                ></div>
              </div>
            </div>
          </section>

          {/* Tabbed Interface */}
          <div className="bg-arctic-surface dark:bg-molten-surface rounded-lg anti-slop-card-light dark:anti-slop-card-dark overflow-hidden transition-colors duration-300">
            
            <div className="border-b border-outline-variant dark:border-[#2A345E] px-gutter">
              <nav className="tab-nav flex gap-8 relative" id="main-tabs">
                <button
                  ref={overviewTabRef}
                  onClick={() => setActiveTab('overview')}
                  className={`tab-btn py-4 font-label-md cursor-pointer transition-all duration-200 ${activeTab === 'overview' ? 'text-primary dark:text-molten-primary font-bold' : 'text-on-surface-variant dark:text-molten-text-muted hover:text-primary'}`}
                >
                  Overview
                </button>
                <button
                  ref={leadsTabRef}
                  onClick={() => setActiveTab('leads')}
                  className={`tab-btn py-4 font-label-md cursor-pointer transition-all duration-200 ${activeTab === 'leads' ? 'text-primary dark:text-molten-primary font-bold' : 'text-on-surface-variant dark:text-molten-text-muted hover:text-primary'}`}
                >
                  Leads
                </button>
                {/* TODO: Campaign Settings (Phase 2/3 edit capability)
                <button
                  ref={settingsTabRef}
                  onClick={() => setActiveTab('settings')}
                  className={`tab-btn py-4 font-label-md cursor-pointer transition-all duration-200 ${activeTab === 'settings' ? 'text-primary dark:text-molten-primary font-bold' : 'text-on-surface-variant dark:text-molten-text-muted hover:text-primary'}`}
                >
                  Settings
                </button>
                */}
                
                {/* Underline Slider */}
                <div 
                  className="tab-slider bg-primary dark:bg-molten-primary transition-all duration-300"
                  style={sliderStyle}
                ></div>
              </nav>
            </div>

            <div className="p-gutter">
              
              {/* Tab 1: Overview Content */}
              {activeTab === 'overview' && (
                <div className="space-y-6 animate-fade-in">
                  <h3 className="font-headline-sm text-headline-sm">Campaign Overview</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="border border-outline-variant dark:border-[#2A345E] rounded-xl p-6 space-y-4 bg-surface-container-lowest dark:bg-molten-surface/40">
                      <h4 className="font-bold text-primary dark:text-molten-primary border-b border-outline-variant dark:border-[#2A345E] pb-2">Resource Allocation</h4>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <p className="text-xs text-arctic-text-muted">Total Budget Allocated</p>
                          <p className="text-xl font-bold tabular-nums">{campaign.budget_credits} credits</p>
                        </div>
                        <div>
                          <p className="text-xs text-arctic-text-muted">Budget Spent</p>
                          <p className="text-xl font-bold tabular-nums text-red-500">{campaign.budget_used_credits || 0} credits</p>
                        </div>
                        <div>
                          <p className="text-xs text-arctic-text-muted">Max Concurrency</p>
                          <p className="text-xl font-bold tabular-nums">{campaign.max_concurrent_calls} channels</p>
                        </div>
                        <div>
                          <p className="text-xs text-arctic-text-muted">Calls per Minute</p>
                          <p className="text-xl font-bold tabular-nums">{campaign.calls_per_minute || 10} calls</p>
                        </div>
                      </div>
                    </div>

                    {/* TODO: Bot configuration editor (Phase 3/4) - disabled in client view */}
                    <div className="border border-outline-variant dark:border-[#2A345E] rounded-xl p-6 space-y-4 bg-surface-container-lowest dark:bg-molten-surface/40">
                      <h4 className="font-bold text-primary dark:text-molten-primary border-b border-outline-variant dark:border-[#2A345E] pb-2">Bot Strategy</h4>
                      <div>
                        <p className="text-xs text-arctic-text-muted">AI Personality Configuration</p>
                        <p className="text-lg font-bold">Sales Specialist Bot</p>
                        <p className="text-xs text-arctic-text-muted mt-1">Pricing Rate: 5 credits/minute</p>
                      </div>
                      <div className="grid grid-cols-2 gap-4 mt-2">
                        <div>
                          <p className="text-xs text-arctic-text-muted">Max Call Attempts</p>
                          <p className="font-bold">{campaign.max_attempts} attempts</p>
                        </div>
                        <div>
                          <p className="text-xs text-arctic-text-muted">Retry Delay</p>
                          <p className="font-bold">{campaign.retry_delay_minutes} minutes</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Tab 2: Leads Content */}
              {activeTab === 'leads' && (
                <div className="flex flex-col gap-gutter animate-fade-in">
                  
                  {/* CSV Upload Zone (Collapsible/Bento Style) */}
                  <div 
                    onDragOver={handleDragOver}
                    onDrop={handleFileDrop}
                    className="bg-arctic-surface dark:bg-molten-surface rounded-xl border border-outline-variant dark:border-[#2A345E] shadow-[0_4px_20px_rgba(22,71,232,0.05)] dark:shadow-none p-6 flex flex-col sm:flex-row items-center gap-6 transition-all duration-300"
                  >
                    <input
                      type="file"
                      ref={fileInputRef}
                      onChange={handleFileBrowse}
                      className="hidden"
                      accept=".csv,.xlsx"
                    />
                    <div className="w-24 h-24 rounded-lg bg-surface-container-low dark:bg-molten-bg border border-outline-variant dark:border-[#2A345E] flex items-center justify-center shrink-0">
                      <span className="material-symbols-outlined text-[48px] text-primary dark:text-molten-primary opacity-80">upload_file</span>
                    </div>
                    <div className="flex-1 text-center sm:text-left">
                      <h3 className="font-headline-sm text-headline-sm font-bold text-on-surface dark:text-molten-text mb-2">Import New Leads</h3>
                      <p className="text-on-surface-variant dark:text-molten-text-muted font-body-sm text-body-sm mb-4">
                        Drag and drop your CSV file here, or click to browse. We will automatically map Name and Phone number columns.
                      </p>
                      {isUploading ? (
                        <div className="flex items-center justify-center sm:justify-start gap-2">
                          <div className="inline-block animate-spin rounded-full h-5 w-5 border-b-2 border-primary"></div>
                          <span className="text-sm font-bold text-primary dark:text-molten-primary">Uploading...</span>
                        </div>
                      ) : (
                        <div className="flex flex-wrap justify-center sm:justify-start gap-3">
                          <button onClick={() => fileInputRef.current?.click()} className="bg-surface-variant dark:bg-surface-variant/20 text-primary dark:text-molten-primary px-4 py-2 rounded-lg font-label-md text-label-md hover:bg-surface-container-high dark:hover:bg-surface-variant/40 transition-colors cursor-pointer">
                            Browse Files
                          </button>
                          {/* TODO: Download Template CSV
                          <button className="text-arctic-text-muted hover:text-on-surface dark:hover:text-molten-text px-4 py-2 rounded-lg font-label-md text-label-md transition-colors cursor-pointer border border-transparent hover:border-outline-variant">
                            Download Template
                          </button>
                          */}
                        </div>
                      )}
                    </div>
                  </div>

                  {uploadResult && (
                    <div className={`p-4 rounded-lg border ${uploadResult.success ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-800 dark:text-emerald-400' : 'bg-rose-500/10 border-rose-500/20 text-rose-800 dark:text-rose-400'}`}>
                      <p className="font-bold mb-2">{uploadResult.message}</p>
                      {uploadResult.details && (
                        <ul className="text-xs space-y-1 list-disc list-inside">
                          <li>Uploaded: <strong>{uploadResult.details.leads_uploaded}</strong> leads</li>
                          <li>Duplicates skipped: <strong>{uploadResult.details.duplicates_skipped}</strong></li>
                          <li>DNC numbers skipped: <strong>{uploadResult.details.dnc_on_upload}</strong></li>
                          <li>Invalid formats skipped: <strong>{uploadResult.details.invalid_phones}</strong></li>
                        </ul>
                      )}
                    </div>
                  )}

                  {/* Leads Table Card */}
                  <div className="bg-arctic-surface dark:bg-molten-surface rounded-xl border border-outline-variant dark:border-[#2A345E] shadow-[0_4px_20px_rgba(22,71,232,0.05)] dark:shadow-none overflow-hidden flex flex-col h-[500px]">
                    <div className="p-4 border-b border-outline-variant dark:border-[#2A345E] flex justify-between items-center bg-surface dark:bg-molten-surface/40">
                      <div className="flex items-center gap-2">
                        <h3 className="font-label-md text-label-md font-bold text-on-surface dark:text-molten-text">Active Leads ({totalLeadsCount.toLocaleString()})</h3>
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="relative">
                          <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline-variant text-sm">search</span>
                          <input 
                            className="pl-9 pr-4 py-1.5 text-sm rounded-lg border border-outline-variant dark:border-[#2A345E] bg-arctic-surface dark:bg-molten-bg text-on-surface dark:text-molten-text focus:border-primary focus:ring-1 focus:ring-primary w-64 outline-none" 
                            placeholder="Search leads..." 
                            type="text"
                            value={leadsSearch}
                            onChange={(e) => setLeadsSearch(e.target.value)}
                          />
                        </div>
                        <button className="p-1.5 rounded border border-outline-variant dark:border-[#2A345E] text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-variant dark:hover:bg-molten-surface transition-colors cursor-pointer">
                          <span className="material-symbols-outlined text-sm">filter_list</span>
                        </button>
                      </div>
                    </div>
                    <div className="flex-1 overflow-auto">
                      <table className="w-full text-left border-collapse">
                        <thead className="sticky top-0 bg-surface-container-low dark:bg-molten-bg border-b border-outline-variant dark:border-[#2A345E] z-10">
                          <tr>
                            <th className="py-3 px-4 font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted font-semibold">Name</th>
                            <th className="py-3 px-4 font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted font-semibold">Phone</th>
                            <th className="py-3 px-4 font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted font-semibold">Status</th>
                            <th className="py-3 px-4 font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted font-semibold">Attempts</th>
                            <th className="py-3 px-4 font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted font-semibold text-right">Actions</th>
                          </tr>
                        </thead>
                        <tbody className="font-body-sm text-body-sm text-on-surface dark:text-molten-text">
                          {leadsLoading ? (
                            <tr>
                              <td colSpan="5" className="px-6 py-8 text-center text-sm text-arctic-text-muted">Loading leads...</td>
                            </tr>
                          ) : (
                            leads.map((lead) => {
                              // Determine status style
                              let statusElement = null;
                              if (lead.status === 'completed') {
                                statusElement = (
                                  <span className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-secondary-container/20 text-on-secondary-container dark:text-emerald-400 text-xs font-semibold">
                                    <svg className="w-6 h-4" viewBox="0 0 24 16">
                                      <rect className="waveform-bar" height="12" rx="1" style={{ animationDelay: '0s' }} width="2" x="0" y="2"></rect>
                                      <rect className="waveform-bar" height="16" rx="1" style={{ animationDelay: '0.2s' }} width="2" x="4" y="0"></rect>
                                      <rect className="waveform-bar" height="10" rx="1" style={{ animationDelay: '0.4s' }} width="2" x="8" y="3"></rect>
                                      <rect className="waveform-bar" height="14" rx="1" style={{ animationDelay: '0.1s' }} width="2" x="12" y="1"></rect>
                                      <rect className="waveform-bar" height="8" rx="1" style={{ animationDelay: '0.3s' }} width="2" x="16" y="4"></rect>
                                      <rect className="waveform-bar" height="12" rx="1" style={{ animationDelay: '0.15s' }} width="2" x="20" y="2"></rect>
                                    </svg>
                                    Connected
                                  </span>
                                );
                              } else if (lead.status === 'failed') {
                                statusElement = (
                                  <span className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-error-container/40 text-on-error-container dark:bg-rose-500/10 dark:text-rose-400 text-xs font-semibold">
                                    <svg className="w-6 h-4" viewBox="0 0 24 16">
                                      <rect className="waveform-bar-static" height="12" rx="1" width="2" x="0" y="2"></rect>
                                      <rect className="waveform-bar-static" height="16" rx="1" width="2" x="4" y="0"></rect>
                                      <rect className="waveform-bar-static" height="10" rx="1" width="2" x="8" y="3"></rect>
                                      <rect className="waveform-bar-static" height="14" rx="1" width="2" x="12" y="1"></rect>
                                      <rect className="waveform-bar-static" height="8" rx="1" width="2" x="16" y="4"></rect>
                                      <rect className="waveform-bar-static" height="12" rx="1" width="2" x="20" y="2"></rect>
                                    </svg>
                                    Failed
                                  </span>
                                );
                              } else if (lead.status === 'calling') {
                                statusElement = (
                                  <span className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-[#FFF0E6] dark:bg-amber-500/10 text-[#D48A00] dark:text-amber-400 text-xs font-semibold border border-[#FFE0CC] dark:border-amber-500/20">
                                    <svg className="w-6 h-4" viewBox="0 0 24 16">
                                      <rect className="waveform-bar" height="12" rx="1" style={{ animationDelay: '0s' }} width="2" x="0" y="2"></rect>
                                      <rect className="waveform-bar" height="16" rx="1" style={{ animationDelay: '0.2s' }} width="2" x="4" y="0"></rect>
                                      <rect className="waveform-bar" height="10" rx="1" style={{ animationDelay: '0.4s' }} width="2" x="8" y="3"></rect>
                                      <rect className="waveform-bar" height="14" rx="1" style={{ animationDelay: '0.1s' }} width="2" x="12" y="1"></rect>
                                      <rect className="waveform-bar" height="8" rx="1" style={{ animationDelay: '0.3s' }} width="2" x="16" y="4"></rect>
                                      <rect className="waveform-bar" height="12" rx="1" style={{ animationDelay: '0.15s' }} width="2" x="20" y="2"></rect>
                                    </svg>
                                    Busy
                                  </span>
                                );
                              } else {
                                statusElement = (
                                  <span className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-surface-variant dark:bg-surface-variant/20 text-on-surface-variant dark:text-molten-text-muted text-xs font-semibold">
                                    <svg className="w-6 h-4" viewBox="0 0 24 16">
                                      <rect className="waveform-bar-static" height="12" rx="1" width="2" x="0" y="2"></rect>
                                      <rect className="waveform-bar-static" height="16" rx="1" width="2" x="4" y="0"></rect>
                                      <rect className="waveform-bar-static" height="10" rx="1" width="2" x="8" y="3"></rect>
                                      <rect className="waveform-bar-static" height="14" rx="1" width="2" x="12" y="1"></rect>
                                      <rect className="waveform-bar-static" height="8" rx="1" width="2" x="16" y="4"></rect>
                                      <rect className="waveform-bar-static" height="12" rx="1" width="2" x="20" y="2"></rect>
                                    </svg>
                                    No Answer
                                  </span>
                                );
                              }

                              return (
                                <tr 
                                  key={lead.id}
                                  className="arctic-table-row hover:bg-surface-container-lowest dark:hover:bg-molten-surface/60 transition-colors cursor-pointer"
                                  onClick={() => handleOpenTranscript(lead)}
                                >
                                  <td className="py-3 px-4 font-medium">{lead.name || '—'}</td>
                                  <td className="py-3 px-4 tabular-nums text-on-surface-variant dark:text-molten-text-muted">{lead.phone}</td>
                                  <td className="py-3 px-4">
                                    {statusElement}
                                  </td>
                                  <td className="py-3 px-4 tabular-nums">{lead.attempts || 0}</td>
                                  <td className="py-3 px-4 text-right">
                                    <button 
                                      className="text-primary dark:text-molten-primary hover:text-primary/80 font-medium text-sm transition-colors cursor-pointer"
                                      onClick={(e) => { e.stopPropagation(); handleOpenTranscript(lead); }}
                                    >
                                      View Details
                                    </button>
                                  </td>
                                </tr>
                              );
                            })
                          )}
                        </tbody>
                      </table>
                    </div>
                    <div className="p-3 border-t border-outline-variant dark:border-[#2A345E] bg-surface dark:bg-molten-surface/40 flex justify-between items-center text-sm text-on-surface-variant dark:text-molten-text-muted">
                      <span>Showing {leads.length > 0 ? leadsOffset + 1 : 0} to {Math.min(leadsOffset + leadsLimit, totalLeadsCount)} of {totalLeadsCount} entries</span>
                      <div className="flex gap-1">
                        <button 
                          disabled={leadsOffset === 0}
                          onClick={() => setLeadsOffset(prev => Math.max(0, prev - leadsLimit))}
                          className="px-3 py-1 border border-outline-variant dark:border-[#2A345E] rounded hover:bg-surface-variant dark:hover:bg-surface-variant/20 disabled:opacity-50 cursor-pointer"
                        >
                          Prev
                        </button>
                        <button className="px-3 py-1 border border-outline-variant dark:border-[#2A345E] rounded bg-primary dark:bg-molten-primary text-on-primary dark:text-molten-bg">1</button>
                        <button className="px-3 py-1 border border-outline-variant dark:border-[#2A345E] rounded hover:bg-surface-variant dark:hover:bg-surface-variant/20 cursor-pointer">2</button>
                        <button 
                          disabled={leadsOffset + leadsLimit >= totalLeadsCount}
                          onClick={() => setLeadsOffset(prev => prev + leadsLimit)}
                          className="px-3 py-1 border border-outline-variant dark:border-[#2A345E] rounded hover:bg-surface-variant dark:hover:bg-surface-variant/20 disabled:opacity-50 cursor-pointer"
                        >
                          Next
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Tab 3: Settings Content */}
              {/* TODO: Tab 3 Settings Content
              {activeTab === 'settings' && (
                <form onSubmit={handleSaveSettings} className="space-y-6 animate-fade-in max-w-xl">
                  <h3 className="font-headline-sm text-headline-sm">Campaign Settings</h3>
                  
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-bold text-on-surface dark:text-molten-text mb-1">Campaign Objective Name</label>
                      <input
                        type="text"
                        className="w-full bg-surface-container-low dark:bg-surface-variant/10 border border-outline-variant dark:border-[#2A345E] rounded-lg p-3 outline-none focus:border-primary dark:focus:border-molten-primary text-on-surface dark:text-molten-text"
                        value={campaign.name}
                        onChange={(e) => setCampaign({ ...campaign, name: e.target.value })}
                        required
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-bold text-on-surface dark:text-molten-text mb-1">Max Concurrent Call channels</label>
                      <input
                        type="number"
                        className="w-full bg-surface-container-low dark:bg-surface-variant/10 border border-outline-variant dark:border-[#2A345E] rounded-lg p-3 outline-none focus:border-primary dark:focus:border-molten-primary text-on-surface dark:text-molten-text"
                        value={campaign.max_concurrent_calls}
                        onChange={(e) => setCampaign({ ...campaign, max_concurrent_calls: Number(e.target.value) })}
                        min="1"
                        max="500"
                        required
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-bold text-on-surface dark:text-molten-text mb-1">Max Call Attempts</label>
                        <input
                          type="number"
                          className="w-full bg-surface-container-low dark:bg-surface-variant/10 border border-outline-variant dark:border-[#2A345E] rounded-lg p-3 outline-none focus:border-primary dark:focus:border-molten-primary text-on-surface dark:text-molten-text"
                          value={campaign.max_attempts || 3}
                          onChange={(e) => setCampaign({ ...campaign, max_attempts: Number(e.target.value) })}
                          min="1"
                          max="10"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-bold text-on-surface dark:text-molten-text mb-1">Retry Delay (min)</label>
                        <input
                          type="number"
                          className="w-full bg-surface-container-low dark:bg-surface-variant/10 border border-outline-variant dark:border-[#2A345E] rounded-lg p-3 outline-none focus:border-primary dark:focus:border-molten-primary text-on-surface dark:text-molten-text"
                          value={campaign.retry_delay_minutes || 120}
                          onChange={(e) => setCampaign({ ...campaign, retry_delay_minutes: Number(e.target.value) })}
                          min="1"
                          max="1440"
                        />
                      </div>
                    </div>
                  </div>

                  <button
                    type="submit"
                    className="px-8 py-3 bg-primary dark:bg-molten-primary text-white dark:text-molten-bg rounded-lg font-bold hover:brightness-110 active:scale-95 transition-all cursor-pointer"
                  >
                    Save Settings
                  </button>
                </form>
              )}
              */}

            </div>
          </div>

        </main>
      </div>

      {/* Manual Add Lead Modal */}
      {isAddLeadOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setIsAddLeadOpen(false)}></div>
          <form onSubmit={handleAddLead} className="relative bg-arctic-surface dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-xl p-6 max-w-md w-full shadow-2xl space-y-4 text-on-surface dark:text-molten-text">
            <h3 className="text-xl font-bold border-b border-outline-variant dark:border-[#2A345E] pb-2">Add New Lead</h3>
            
            <div>
              <label className="block text-xs text-arctic-text-muted mb-1">Full Name</label>
              <input
                type="text"
                className="w-full bg-surface-container-low dark:bg-surface-variant/10 border border-outline-variant dark:border-[#2A345E] p-2 rounded outline-none focus:border-primary"
                value={newLead.name}
                onChange={(e) => setNewLead({ ...newLead, name: e.target.value })}
                placeholder="e.g. Rahul Patil"
              />
            </div>

            <div>
              <label className="block text-xs text-arctic-text-muted mb-1">Phone Number (with prefix)</label>
              <input
                type="tel"
                className="w-full bg-surface-container-low dark:bg-surface-variant/10 border border-outline-variant dark:border-[#2A345E] p-2 rounded outline-none focus:border-primary font-mono"
                value={newLead.phone}
                onChange={(e) => setNewLead({ ...newLead, phone: e.target.value })}
                placeholder="e.g. +919988776655"
                required
              />
            </div>

            <div>
              <label className="block text-xs text-arctic-text-muted mb-1">Lead Type</label>
              <select
                value={newLead.lead_type}
                onChange={(e) => setNewLead({ ...newLead, lead_type: e.target.value })}
                className="w-full bg-surface-container-low dark:bg-surface-variant/10 border border-outline-variant dark:border-[#2A345E] p-2 rounded outline-none"
              >
                <option value="cold">Cold</option>
                <option value="warm">Warm</option>
                <option value="hot">Hot</option>
              </select>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setIsAddLeadOpen(false)}
                className="px-4 py-2 hover:bg-surface-container rounded cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-6 py-2 bg-primary text-white rounded cursor-pointer font-bold hover:brightness-110"
              >
                Add Contact
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Mobile BottomNavBar */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-arctic-surface dark:bg-molten-surface border-t border-outline-variant dark:border-[#2A345E] flex justify-around items-center py-3 z-50">
        <Link className="flex flex-col items-center gap-1 text-on-surface-variant dark:text-molten-text-muted" to="/app">
          <span className="material-symbols-outlined">dashboard</span>
          <span className="text-[10px]">Home</span>
        </Link>
        <button className="flex flex-col items-center gap-1 text-primary dark:text-molten-primary font-bold">
          <span className="material-symbols-outlined fill-icon">analytics</span>
          <span className="text-[10px]">Leads</span>
        </button>
        <Link className="flex flex-col items-center gap-1 text-on-surface-variant dark:text-molten-text-muted" to="/app/calls">
          <span className="material-symbols-outlined">list_alt</span>
          <span className="text-[10px]">Logs</span>
        </Link>
        {/* TODO: Mobile settings
        <button className="flex flex-col items-center gap-1 text-on-surface-variant dark:text-molten-text-muted">
          <span className="material-symbols-outlined">settings</span>
          <span className="text-[10px]">Settings</span>
        </button>
        */}
      </nav>

      <CallTranscriptDrawer
        isOpen={isTranscriptOpen}
        sessionCallId={selectedLeadForTranscript ? (selectedLeadForTranscript.session_call_id || selectedLeadForTranscript.id) : null}
        leadName={selectedLeadForTranscript ? selectedLeadForTranscript.name : ''}
        onClose={() => setIsTranscriptOpen(false)}
      />

    </div>
  );
};

export default CampaignDetail;
