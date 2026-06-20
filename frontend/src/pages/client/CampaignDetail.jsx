import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useTheme } from '../../hooks/useTheme';
import { useToast } from '../../contexts/ToastContext';
import clientApi from '../../api/client';
import LoaderOverlay from '../../components/shared/LoaderOverlay';
import CallTranscriptDrawer from '../../components/shared/CallTranscriptDrawer';

const CampaignDetail = () => {
  const { id } = useParams();
  const { theme, toggleTheme } = useTheme();
  const { showToast } = useToast();

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

  // Edit Lead Modal State
  const [isEditLeadOpen, setIsEditLeadOpen] = useState(false);
  const [editLeadData, setEditLeadData] = useState(null);

  // Ticking calling counter animation state
  const [liveCallingCount, setLiveCallingCount] = useState(0);

  // Resume Confirmation Modal State
  const [isStartConfirmOpen, setIsStartConfirmOpen] = useState(false);

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


  // Tab slider sizing refs
  const overviewTabRef = useRef(null);
  const leadsTabRef = useRef(null);
  const settingsTabRef = useRef(null);
  const [sliderStyle, setSliderStyle] = useState({});

  // hidden file input ref
  const fileInputRef = useRef(null);

  // Load campaign & stats details
  const loadCampaignDetails = useCallback(async (showSpinner = true) => {
    if (showSpinner) setLoading(true);
    try {
      const response = await clientApi.get(`/api/campaigns/${id}/stats`);
      if (response.data && response.data.stats) {
        setCampaign(response.data.stats);
        setLiveCallingCount(response.data.stats.calling_leads || 0);
      } else {
        setCampaign(null);
      }
    } catch (err) {
      console.warn('API error fetching campaign', err);
      setCampaign(null);
    } finally {
      if (showSpinner) setLoading(false);
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
          search: leadsSearch || undefined,
        }
      });
      if (response.data) {
        setLeads(response.data.leads || []);
        setTotalLeadsCount(response.data.total_count || 0);
      } else {
        setLeads([]);
        setTotalLeadsCount(0);
      }
    } catch (err) {
      console.warn('API error listing leads', err);
      setLeads([]);
      setTotalLeadsCount(0);
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

  // Real-time polling for campaign stats
  useEffect(() => {
    if (!campaign) return;
    const isPausing = campaign.status === 'pausing' || (campaign.status === 'paused' && campaign.calling_leads > 0);
    if (campaign.status !== 'running' && !isPausing) return;
    
    const pollInterval = isPausing ? 3000 : 10000;
    const interval = setInterval(() => {
      loadCampaignDetails(false);
    }, pollInterval);
    return () => clearInterval(interval);
  }, [campaign, loadCampaignDetails]);

  const handleOpenTranscript = (lead) => {
    setSelectedLeadForTranscript(lead);
    setIsTranscriptOpen(true);
  };

  // Actions
  // Actions
  const handleToggleState = async () => {
    if (!campaign) return;
    const action = campaign.status === 'running' ? 'stop' : 'start';
    if (action === 'start') {
      setIsStartConfirmOpen(true);
      return;
    }

    try {
      const response = await clientApi.patch(`/api/campaigns/${id}/stop`);
      if (response.data) {
        showToast('Campaign paused successfully.', 'success');
        loadCampaignDetails();
        return;
      }
    } catch (err) {
      console.warn('Campaign pause failed.', err);
      showToast(err.customErrorMessage || 'Failed to pause campaign.', 'error');
    }
  };

  const handleConfirmStart = async () => {
    try {
      const response = await clientApi.patch(`/api/campaigns/${id}/start`);
      if (response.data) {
        showToast('Campaign started successfully.', 'success');
        setIsStartConfirmOpen(false);
        loadCampaignDetails();
        return;
      }
    } catch (err) {
      console.warn('Campaign start failed.', err);
      showToast(err.customErrorMessage || 'Failed to start campaign.', 'error');
    }
  };

  const handleCancelCampaign = async () => {
    if (!window.confirm('Are you sure you want to cancel this campaign? Any allocated remaining budget will be refunded.')) return;
    
    try {
      const response = await clientApi.patch(`/api/campaigns/${id}/cancel`);
      if (response.data) {
        showToast('Campaign cancelled successfully.', 'success');
        loadCampaignDetails();
        return;
      }
    } catch (err) {
      console.warn('Campaign cancel endpoint failed.', err);
      showToast(err.customErrorMessage || 'Failed to cancel campaign.', 'error');
    }
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
        showToast('Leads uploaded successfully.', 'success');
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
      showToast(err.customErrorMessage || 'Failed to upload leads. Please verify file formatting.', 'error');
      setUploadResult({
        success: false,
        message: err.customErrorMessage || 'Failed to upload leads. Please verify file formatting.'
      });
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

        showToast('Lead added successfully.', 'success');
        setIsAddLeadOpen(false);
        setNewLead({ name: '', phone: '', lead_type: 'cold', metadata: {} });
        loadLeads();
        loadCampaignDetails();
        return;
      }
    } catch (err) {
      console.warn('Manual lead add endpoint failed.', err);
      showToast(err.customErrorMessage || 'Failed to add lead. Please try again.', 'error');
    }
  };

  // Edit Lead
  const handleEditLead = async (e) => {
    e.preventDefault();
    if (!editLeadData.name?.trim()) return;

    try {
      // 1. Update basic fields
      await clientApi.patch(`/api/campaigns/${id}/leads/${editLeadData.id}`, {
        name: editLeadData.name,
        lead_type: editLeadData.lead_type || 'cold'
      });

      // 2. Update status if changed
      if (editLeadData.status && editLeadData.status !== editLeadData.original_status) {
        await clientApi.patch(`/api/campaigns/${id}/leads/${editLeadData.id}/status`, {
          status: editLeadData.status
        });
      }

      showToast('Lead updated successfully.', 'success');
      setIsEditLeadOpen(false);
      setEditLeadData(null);
      loadLeads();
      loadCampaignDetails();
    } catch (err) {
      console.error('Failed to edit lead', err);
      showToast(err.customErrorMessage || 'Failed to edit lead. Transition may not be allowed.', 'error');
    }
  };

  // Delete Lead
  const handleDeleteLead = async (leadId) => {
    if (!window.confirm('Are you sure you want to delete this lead?')) return;
    
    try {
      const response = await clientApi.delete(`/api/campaigns/${id}/leads/${leadId}`);
      if (response.data) {
        showToast('Lead deleted successfully.', 'success');
        loadLeads();
        loadCampaignDetails();
      }
    } catch (err) {
      console.error('Failed to delete lead', err);
      showToast(err.customErrorMessage || 'Failed to delete lead. It may be currently active.', 'error');
    }
  };

  // Change Lead Status
  const handleChangeLeadStatus = async (leadId, newStatus) => {
    try {
      const response = await clientApi.patch(`/api/campaigns/${id}/leads/${leadId}/status`, {
        status: newStatus
      });
      if (response.data) {
        showToast('Status updated successfully.', 'success');
        loadLeads();
        loadCampaignDetails();
      }
    } catch (err) {
      console.error('Failed to change lead status', err);
      showToast(err.customErrorMessage || 'Failed to change lead status. The transition may not be allowed.', 'error');
    }
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
        showToast('Settings updated successfully!', 'success');
        loadCampaignDetails();
        return;
      }
    } catch (err) {
      console.warn('API PATCH campaign failed.', err);
      showToast(err.customErrorMessage || 'Failed to save settings.', 'error');
    }
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

  const isPausing = campaign.status === 'pausing' || (campaign.status === 'paused' && campaign.calling_leads > 0);

  return (
    <>
      <LoaderOverlay isVisible={isPausing} message="Finishing ongoing leads..." />
      <div className="flex-1 w-full">
          
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

                {(campaign.status === 'paused' || campaign.status === 'pausing') && (
                  <span className="status-pulse-container px-3 py-1 bg-amber-500/10 text-amber-600 dark:text-amber-400 font-label-sm text-label-sm rounded-full border border-amber-500/20 flex items-center gap-1 transition-all duration-500">
                    <span className="w-1.5 h-1.5 bg-amber-500 rounded-full"></span>
                    <span className="status-text">{campaign.status === 'pausing' ? 'Pausing...' : 'Paused'}</span>
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
                Campaign ID: {campaign.id} • Started {campaign.created_at ? new Date(campaign.created_at).toLocaleDateString() : 'N/A'}
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

          {/* Metric Cards */}
          <section className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-gutter mb-stack-lg">
            {/* Total Leads */}
            <div className="stagger-in bg-arctic-surface dark:bg-molten-surface p-6 anti-slop-card-light dark:anti-slop-card-dark transition-colors duration-300" style={{ animationDelay: '0.1s' }}>
              <p className="text-arctic-text-muted dark:text-molten-text-muted font-label-md mb-2">Total Leads</p>
              <div className="flex items-baseline gap-2 mb-4">
                <span className="text-headline-md font-bold tabular-nums">{total.toLocaleString()}</span>
                {/* <span className="text-label-sm text-secondary">+12%</span> */}
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

            {/* Budget Allocated */}
            <div className="stagger-in bg-arctic-surface dark:bg-molten-surface p-6 anti-slop-card-light dark:anti-slop-card-dark transition-colors duration-300" style={{ animationDelay: '0.5s' }}>
              <p className="text-arctic-text-muted dark:text-molten-text-muted font-label-md mb-2">Total Credits</p>
              <div className="flex items-baseline gap-2 mb-4">
                <span className="text-headline-md font-bold tabular-nums">{(campaign.budget_credits || 0).toLocaleString()}</span>
                <span className="text-label-sm text-secondary">Allocated</span>
              </div>
              <div className="h-1.5 w-full bg-surface-container-highest dark:bg-[#1f2937] rounded-full overflow-hidden">
                <div 
                  className="h-full transition-all duration-1000 cubic-bezier(0.16, 1, 0.3, 1) bg-blue-500" 
                  style={{ width: '100%' }}
                ></div>
              </div>
            </div>

            {/* Budget Spent */}
            <div className="stagger-in bg-arctic-surface dark:bg-molten-surface p-6 anti-slop-card-light dark:anti-slop-card-dark transition-colors duration-300" style={{ animationDelay: '0.6s' }}>
              <p className="text-arctic-text-muted dark:text-molten-text-muted font-label-md mb-2">Credits Used</p>
              <div className="flex items-baseline gap-2 mb-4">
                <span className="text-headline-md font-bold tabular-nums text-error">{(campaign.budget_used_credits || 0).toLocaleString()}</span>
                <span className="text-label-sm text-error">Spent</span>
              </div>
              <div className="h-1.5 w-full bg-surface-container-highest dark:bg-[#1f2937] rounded-full overflow-hidden">
                <div 
                  className="h-full transition-all duration-1000 cubic-bezier(0.16, 1, 0.3, 1) bg-error" 
                  style={{ width: `${campaign.budget_credits > 0 ? ((campaign.budget_used_credits || 0) / campaign.budget_credits) * 100 : 0}%` }}
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
                        <p className="text-lg font-bold">{campaign.bot_config?.name || 'Assigned Bot'}</p>
                        {campaign.bot_config?.credits_per_minute && (
                          <p className="text-xs text-arctic-text-muted mt-1">Pricing Rate: {campaign.bot_config.credits_per_minute} credits/minute</p>
                        )}
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
                  {(campaign.status === 'draft' || campaign.status === 'paused') ? (
                    <>
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
                          <button 
                            onClick={() => setIsAddLeadOpen(true)}
                            className="border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text hover:bg-surface-container dark:hover:bg-[#2A345E]/50 px-4 py-2 rounded-lg font-label-md text-label-md transition-colors cursor-pointer"
                          >
                            Add Lead Manually
                          </button>
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

                          <li>Invalid formats skipped: <strong>{uploadResult.details.invalid_phones}</strong></li>
                        </ul>
                      )}
                    </div>
                  )}
                    </>
                  ) : (
                    <div className="bg-arctic-surface dark:bg-molten-surface rounded-xl border border-outline-variant dark:border-[#2A345E] p-6 text-center text-arctic-text-muted dark:text-molten-text-muted">
                      Campaign modifications (Import/Add leads) are locked while the campaign is active, completed, or cancelled.
                    </div>
                  )}

                  {/* Leads Table Card */}
                  <div className="bg-arctic-surface dark:bg-molten-surface rounded-xl border border-outline-variant dark:border-[#2A345E] shadow-[0_4px_20px_rgba(22,71,232,0.05)] dark:shadow-none overflow-hidden flex flex-col h-[500px]">
                    <div className="p-4 border-b border-outline-variant dark:border-[#2A345E] flex justify-between items-center bg-surface dark:bg-molten-surface/40">
                      <div className="flex items-center gap-4">
                        <h3 className="font-label-md text-label-md font-bold text-on-surface dark:text-molten-text">Active Leads ({totalLeadsCount.toLocaleString()})</h3>
                        {(campaign.status === 'draft' || campaign.status === 'paused') && (
                          <button 
                            onClick={() => setIsAddLeadOpen(true)}
                            className="bg-primary/15 hover:bg-primary/25 dark:bg-molten-primary/10 dark:hover:bg-molten-primary/20 text-primary dark:text-molten-primary px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1 active:scale-95"
                          >
                            <span className="material-symbols-outlined text-[14px]">person_add</span>
                            Add Contact
                          </button>
                        )}
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
                          ) : leads.length === 0 ? (
                            <tr>
                              <td colSpan="5" className="px-6 py-12 text-center">
                                <div className="flex flex-col items-center justify-center">
                                  <div className="w-12 h-12 bg-surface-variant dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-full flex items-center justify-center mb-3">
                                    <span className="material-symbols-outlined text-arctic-text-muted dark:text-molten-text-muted text-2xl">person_off</span>
                                  </div>
                                  <p className="text-on-surface-variant dark:text-molten-text-muted font-medium mb-1">No leads found</p>
                                  <p className="text-sm text-arctic-text-muted dark:text-molten-text-muted max-w-xs">Try adjusting your search or filter, or add new leads to this campaign.</p>
                                </div>
                              </td>
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
                              } else if (lead.status === 'callback_scheduled') {
                                statusElement = (
                                  <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-blue-500/10 text-blue-600 dark:text-blue-400 text-xs font-semibold border border-blue-500/20">
                                    <span className="material-symbols-outlined text-[14px]">calendar_clock</span>
                                    {lead.scheduled_callback_at ? `Callback at ${new Date(lead.scheduled_callback_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}` : 'Callback Scheduled'}
                                  </span>
                                );
                              } else if (lead.status === 'pending') {
                                statusElement = (
                                  <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-surface-variant dark:bg-surface-variant/20 text-on-surface-variant dark:text-molten-text-muted text-xs font-semibold border border-outline-variant/30">
                                    <span className="material-symbols-outlined text-[14px]">hourglass_top</span>
                                    Pending
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
                                    <div className="flex items-center justify-end gap-2">
                                      {(lead.status === 'pending' || lead.status === 'callback_scheduled') ? (
                                        <>
                                          <button 
                                            className="text-on-surface-variant dark:text-molten-text-muted hover:text-primary dark:hover:text-molten-primary transition-colors cursor-pointer p-1"
                                            title="Edit Lead"
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              setEditLeadData({ ...lead, original_status: lead.status });
                                              setIsEditLeadOpen(true);
                                            }}
                                          >
                                            <span className="material-symbols-outlined text-[20px]">edit</span>
                                          </button>
                                          <button 
                                            className="text-on-surface-variant dark:text-molten-text-muted hover:text-error dark:hover:text-rose-400 transition-colors cursor-pointer p-1"
                                            title="Delete Lead"
                                            onClick={(e) => { e.stopPropagation(); handleDeleteLead(lead.id); }}
                                          >
                                            <span className="material-symbols-outlined text-[20px]">delete</span>
                                          </button>
                                        </>
                                      ) : (
                                        <span title="Actions locked for started leads" className="text-outline-variant p-1 cursor-not-allowed opacity-50 flex items-center">
                                          <span className="material-symbols-outlined text-[20px]">lock</span>
                                        </span>
                                      )}
                                      <button 
                                        className="text-primary dark:text-molten-primary hover:text-primary/80 font-medium text-sm transition-colors cursor-pointer ml-2"
                                        title="View Transcript"
                                        onClick={(e) => { e.stopPropagation(); handleOpenTranscript(lead); }}
                                      >
                                        View Details
                                      </button>
                                    </div>
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

            </div>
          </div>

        </div>

      {/* Manual Add Lead Modal */}
      {isAddLeadOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-[#0c1941]/40 dark:bg-black/60 backdrop-blur-sm" onClick={() => setIsAddLeadOpen(false)}></div>
          <form onSubmit={handleAddLead} className="relative bg-arctic-surface dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-xl p-6 max-w-md w-full shadow-2xl space-y-4 text-on-surface dark:text-molten-text animate-fade-in">
            <h3 className="text-xl font-bold border-b border-outline-variant dark:border-[#2A345E] pb-2 text-on-surface dark:text-molten-text">Add New Lead</h3>
            
            <div>
              <label className="block text-xs text-arctic-text-muted dark:text-molten-text-muted mb-1 font-semibold">Full Name</label>
              <input
                type="text"
                className="w-full bg-surface-container-low dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] p-2.5 rounded-lg outline-none focus:border-primary dark:focus:border-molten-primary text-on-surface dark:text-molten-text"
                value={newLead.name}
                onChange={(e) => setNewLead({ ...newLead, name: e.target.value })}
                placeholder="e.g. Rahul Patil"
              />
            </div>

            <div>
              <label className="block text-xs text-arctic-text-muted dark:text-molten-text-muted mb-1 font-semibold">Phone Number (with prefix)</label>
              <input
                type="tel"
                className="w-full bg-surface-container-low dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] p-2.5 rounded-lg outline-none focus:border-primary dark:focus:border-molten-primary text-on-surface dark:text-molten-text font-mono"
                value={newLead.phone}
                onChange={(e) => setNewLead({ ...newLead, phone: e.target.value })}
                placeholder="e.g. +919988776655"
                required
              />
            </div>

            <div>
              <label className="block text-xs text-arctic-text-muted dark:text-molten-text-muted mb-1 font-semibold">Lead Type</label>
              <select
                value={newLead.lead_type}
                onChange={(e) => setNewLead({ ...newLead, lead_type: e.target.value })}
                className="w-full bg-surface-container-low dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] p-2.5 rounded-lg outline-none focus:border-primary dark:focus:border-molten-primary text-on-surface dark:text-molten-text"
              >
                <option className="dark:bg-[#1A1C24]" value="cold">Cold</option>
                <option className="dark:bg-[#1A1C24]" value="warm">Warm</option>
                <option className="dark:bg-[#1A1C24]" value="hot">Hot</option>
              </select>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setIsAddLeadOpen(false)}
                className="px-4 py-2 text-on-surface-variant dark:text-molten-text-muted border border-outline-variant dark:border-[#2A345E] hover:bg-surface-container dark:hover:bg-[#2A345E]/50 rounded-lg cursor-pointer transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-6 py-2 bg-primary dark:bg-molten-primary text-on-primary dark:text-molten-bg rounded-lg cursor-pointer font-bold hover:brightness-110 transition-all"
              >
                Add Contact
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Edit Lead Modal */}
      {isEditLeadOpen && editLeadData && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setIsEditLeadOpen(false)}></div>
          <form onSubmit={handleEditLead} className="relative bg-arctic-surface dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-xl p-6 max-w-md w-full shadow-2xl space-y-4 text-on-surface dark:text-molten-text animate-fade-in">
            <h3 className="text-xl font-bold border-b border-outline-variant dark:border-[#2A345E] pb-2 text-on-surface dark:text-molten-text">Edit Lead</h3>
            
            <div>
              <label className="block text-xs text-arctic-text-muted dark:text-molten-text-muted mb-1 font-semibold">Full Name</label>
              <input
                type="text"
                className="w-full bg-surface-container-low dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] p-2.5 rounded-lg outline-none focus:border-primary dark:focus:border-molten-primary text-on-surface dark:text-molten-text"
                value={editLeadData.name || ''}
                onChange={(e) => setEditLeadData({ ...editLeadData, name: e.target.value })}
                placeholder="e.g. Rahul Patil"
              />
            </div>

            <div>
              <label className="block text-xs text-arctic-text-muted dark:text-molten-text-muted mb-1 font-semibold">Phone Number (with prefix)</label>
              <input
                type="tel"
                className="w-full bg-surface-container-low dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] p-2.5 rounded-lg outline-none focus:border-primary dark:focus:border-molten-primary text-on-surface dark:text-molten-text font-mono opacity-50 cursor-not-allowed"
                value={editLeadData.phone}
                disabled
              />
            </div>

            <div>
              <label className="block text-xs text-arctic-text-muted dark:text-molten-text-muted mb-1 font-semibold">Lead Type</label>
              <select
                value={editLeadData.lead_type || 'cold'}
                onChange={(e) => setEditLeadData({ ...editLeadData, lead_type: e.target.value })}
                className="w-full bg-surface-container-low dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] p-2.5 rounded-lg outline-none focus:border-primary dark:focus:border-molten-primary text-on-surface dark:text-molten-text"
              >
                <option className="dark:bg-[#1A1C24]" value="cold">Cold</option>
                <option className="dark:bg-[#1A1C24]" value="warm">Warm</option>
                <option className="dark:bg-[#1A1C24]" value="hot">Hot</option>
              </select>
            </div>

            <div>
              <label className="block text-xs text-arctic-text-muted dark:text-molten-text-muted mb-1 font-semibold">Status</label>
              <select
                value={editLeadData.status || 'pending'}
                onChange={(e) => setEditLeadData({ ...editLeadData, status: e.target.value })}
                className="w-full bg-surface-container-low dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] p-2.5 rounded-lg outline-none focus:border-primary dark:focus:border-molten-primary text-on-surface dark:text-molten-text"
              >
                <option className="dark:bg-[#1A1C24]" value="pending">Pending</option>
                <option className="dark:bg-[#1A1C24]" value="failed">Failed</option>
                <option className="dark:bg-[#1A1C24]" value="dnc">DNC</option>
                <option className="dark:bg-[#1A1C24]" value="completed">Completed</option>
                <option className="dark:bg-[#1A1C24]" value="callback_scheduled">Callback Scheduled</option>
                {/* Prevent selecting calling manually */}
                {editLeadData.status === 'calling' && <option className="dark:bg-[#1A1C24]" value="calling" disabled>Calling (In Progress)</option>}
              </select>
              {editLeadData.status !== editLeadData.original_status && (
                <p className="text-[10px] text-amber-500 mt-1">Status change may require confirmation.</p>
              )}
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setIsEditLeadOpen(false)}
                className="px-4 py-2 text-on-surface-variant dark:text-molten-text-muted border border-outline-variant dark:border-[#2A345E] hover:bg-surface-container dark:hover:bg-[#2A345E]/50 rounded-lg cursor-pointer transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-6 py-2 bg-primary dark:bg-molten-primary text-on-primary dark:text-molten-bg rounded-lg cursor-pointer font-bold hover:brightness-110 transition-all"
              >
                Save Changes
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Resume Campaign Confirmation Modal */}
      {isStartConfirmOpen && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-[#0c1941]/40 dark:bg-black/60 backdrop-blur-sm animate-fade-in" onClick={() => setIsStartConfirmOpen(false)}></div>
          <div className="relative bg-arctic-surface dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-5 text-on-surface dark:text-molten-text animate-scale-up">
            
            {/* Modal Header */}
            <div className="flex items-center gap-3 border-b border-outline-variant dark:border-[#2A345E] pb-3">
              <div className="w-10 h-10 rounded-full bg-primary/10 dark:bg-molten-primary/10 text-primary dark:text-molten-primary flex items-center justify-center shrink-0">
                <span className="material-symbols-outlined text-[24px] animate-pulse">play_circle</span>
              </div>
              <div>
                <h3 className="text-lg font-bold">Start Outbound Dialer</h3>
                <p className="text-xs text-arctic-text-muted dark:text-molten-text-muted">Campaign: {campaign.name}</p>
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
                  <span className="font-bold">{campaign.max_concurrent_calls} channels</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-arctic-text-muted dark:text-molten-text-muted">Calls / Minute:</span>
                  <span className="font-bold">{campaign.calls_per_minute || 10} calls</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-arctic-text-muted dark:text-molten-text-muted">Attempts Limit:</span>
                  <span className="font-bold">{campaign.max_attempts || 3} attempts</span>
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
                onClick={() => setIsStartConfirmOpen(false)}
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



      <CallTranscriptDrawer
        isOpen={isTranscriptOpen}
        sessionCallId={selectedLeadForTranscript ? (selectedLeadForTranscript.session_call_id || selectedLeadForTranscript.id) : null}
        leadName={selectedLeadForTranscript ? selectedLeadForTranscript.name : ''}
        onClose={() => setIsTranscriptOpen(false)}
      />

    </>
  );
};

export default CampaignDetail;
