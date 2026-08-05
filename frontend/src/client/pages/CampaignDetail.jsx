import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useTheme } from '../hooks/useTheme';

import { useToast } from '../../contexts/ToastContext';
import { useDashboardData } from '../../contexts/DashboardDataContext';
import clientApi from '../../api/client';
import LoaderOverlay from '../components/LoaderOverlay';
import CallTranscriptDrawer from '../components/CallTranscriptDrawer';
import { Modal, Button } from '../../components/enterprise';
import CustomMetadataFields from '../../components/client/CustomMetadataFields';
import { buildMetadataFromCustomFields } from '../../utils/leadFormHelpers';
import { sortLeadsCallStack } from '../../pages/client/LeadSheet/leadUtils';
import { buildTurnsByLead, getLeadTurns } from '../utils/computeTurns';

/** Friendly labels for canonical backend outcomes (call_outcomes.py / ┬º1.2). */
const OUTCOME_LABELS = {
  Interested: 'Interested',
  Not_Interested: 'Not Interested',
  Callback_Requested: 'Callback',
  Wrong_Requirement: 'Wrong Requirement',
  Busy: 'Busy',
  No_Answer: 'No Answer',
  Rejected: 'Rejected',
  Carrier_Failed: 'Carrier Failed',
  Unknown: 'Unknown',
  Early_Disconnect: 'Hung up early',
  Max_Attempts_Reached: 'Max Attempts Reached',
  Campaign_Cancelled: 'Campaign Cancelled',
};

function normalizeOutcome(outcome) {
  const raw = (outcome || '').toString().trim();
  if (!raw) return '';
  const lower = raw.toLowerCase();
  if (lower === 'voicemail_detected' || lower === 'voicemail detected' || lower === 'voicemail') return 'Voicemail';
  if (lower === 'callback_requested' || lower === 'callback requested' || lower === 'callback_scheduled' || lower === 'callback scheduled') return 'Callback_Requested';
  if (lower === 'not_interested' || lower === 'not interested') return 'Not_Interested';
  if (lower === 'interested' || lower === 'interest') return 'Interested';
  if (lower === 'early_disconnect' || lower === 'early disconnect') return 'Early_Disconnect';
  if (lower === 'no_answer' || lower === 'no answer' || lower === 'cancel' || lower === 'no-answer') return 'No_Answer';
  if (lower === 'carrier_failed' || lower === 'carrier failed' || lower.includes('carrier') || lower.includes('failed')) return 'Carrier_Failed';
  if (lower === 'wrong_requirement' || lower === 'wrong requirement' || lower === 'wrong_number' || lower === 'wrong number') return 'Wrong_Requirement';
  if (lower === 'rejected') return 'Rejected';
  if (lower === 'transferred') return 'Transferred';
  if (lower === 'unknown') return 'Unknown';
  return raw;
}

function friendlyOutcome(outcome, fallback = 'Unknown') {
  const key = normalizeOutcome(outcome);
  if (!key) return fallback;
  return OUTCOME_LABELS[key] || key.replace(/_/g, ' ');
}

function formatCallbackTiming(nextAt) {
  if (!nextAt) return 'Callback scheduled';
  const target = new Date(nextAt);
  const diffMs = target - new Date();
  if (diffMs <= 0) return 'Callback due';
  const mins = Math.ceil(diffMs / 60000);
  if (mins < 60) return `Callback in ${mins} min`;
  const hours = Math.ceil(mins / 60);
  if (hours < 48) return `Callback in ${hours}h`;
  return `Callback at ${target.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`;
}

function buildCallbackBadgeLabel(lead) {
  const outcome = (lead.outcome || '').toString();
  const duration = lead.last_call_duration_seconds;
  const timing = formatCallbackTiming(lead.next_attempt_at || lead.scheduled_callback_at);
  if (outcome === 'Early_Disconnect' && duration != null) {
    return `Hung up early (${duration}s) ┬╖ ${timing}`;
  }
  if (outcome === 'Callback_Requested') {
    return `${friendlyOutcome(outcome)} ┬╖ ${timing}`;
  }
  if (outcome) {
    return `${friendlyOutcome(outcome)} ┬╖ ${timing}`;
  }
  return timing;
}

const CampaignDetail = () => {
  const { id } = useParams();
  const { theme, toggleTheme } = useTheme();
  const { showToast } = useToast();
  const { calls: dashboardCalls } = useDashboardData();

  // Campaign Details & UI State
  const [campaign, setCampaign] = useState(null);
  const [leads, setLeads] = useState([]);
  const [liveCallingLeads, setLiveCallingLeads] = useState([]);
  const liveCallingLeadsRef = useRef([]);
  const [totalLeadsCount, setTotalLeadsCount] = useState(0);
  const [leadsLimit, setLeadsLimit] = useState(50);
  const [leadsOffset, setLeadsOffset] = useState(0);
  const [leadsSearch, setLeadsSearch] = useState('');
  const [leadsStatusFilter, setLeadsStatusFilter] = useState('');
  const [leadsOutcomeFilter, setLeadsOutcomeFilter] = useState('');
  const [outcomes, setOutcomes] = useState([]);
  const [leadsAttemptsFilter, setLeadsAttemptsFilter] = useState('');
  const [leadsTurnsFilter, setLeadsTurnsFilter] = useState('');

  const [loading, setLoading] = useState(true);
  const [leadsLoading, setLeadsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('leads'); // default tab
  const [isUploading, setIsUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);

  // Transcript drawer state
  const [selectedLeadForTranscript, setSelectedLeadForTranscript] = useState(null);
  const [isTranscriptOpen, setIsTranscriptOpen] = useState(false);

  const isPausing = campaign?.status === 'pausing' || (campaign?.status === 'paused' && campaign?.calling_leads > 0);

  // Manual Add Lead Modal State
  const [isAddLeadOpen, setIsAddLeadOpen] = useState(false);
  const [newLead, setNewLead] = useState({ name: '', phone: '', lead_type: 'cold', metadata: {} });
  const [addLeadCustomColumns, setAddLeadCustomColumns] = useState([]);

  // Edit Lead Modal State
  const [isEditLeadOpen, setIsEditLeadOpen] = useState(false);
  const [editLeadData, setEditLeadData] = useState(null);

  // Ticking calling counter animation state
  const [liveCallingCount, setLiveCallingCount] = useState(0);

  // Resume Confirmation Modal State
  const [isStartConfirmOpen, setIsStartConfirmOpen] = useState(false);

  // Release stuck leads modal state
  const [isReleaseStuckOpen, setIsReleaseStuckOpen] = useState(false);
  const [isReleasingStuck, setIsReleasingStuck] = useState(false);

  // Expandable secondary KPIs
  const [showMoreStats, setShowMoreStats] = useState(false);

  // IST Compliance window state
  const [istStatus, setIstStatus] = useState({ isInside: true, formattedIst: '' });

  const getDynamicLeadFields = useCallback(() => {
    const schema = campaign?.bot_config?.lead_schema;
    if (!schema) return [];
    if (schema.fields && Array.isArray(schema.fields)) return schema.fields;

    return Object.entries(schema).map(([key, value]) => {
      if (typeof value === 'object') {
        return { key, ...value };
      }
      return null;
    }).filter(f => f !== null);
  }, [campaign]);

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
        console.log(response.data.stats);
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

  // Load leads — live concurrent calling rows are fetched separately and always pinned on top
  const loadLeads = useCallback(async (showSpinner = true) => {
    if (showSpinner) setLeadsLoading(true);
    try {
      const isLiveCampaign =
        campaign?.status === 'running' ||
        campaign?.status === 'pausing' ||
        (campaign?.status === 'paused' && (campaign?.calling_leads || 0) > 0);

      // Always pull calling leads while campaign is live — independent of filters/search/page
      let nextCalling = liveCallingLeadsRef.current;
      if (isLiveCampaign) {
        try {
          const callingRes = await clientApi.get(`/api/campaigns/${id}/leads`, {
            params: { limit: 100, offset: 0, status: 'calling' },
          });
          nextCalling = sortLeadsCallStack(callingRes.data?.leads || [], { live: true });
          liveCallingLeadsRef.current = nextCalling;
          setLiveCallingLeads(nextCalling);
        } catch {
          // Keep previous liveCallingLeads so concurrent rows never blink away on a failed poll
          nextCalling = liveCallingLeadsRef.current;
        }
      } else if (campaign) {
        nextCalling = [];
        liveCallingLeadsRef.current = [];
        setLiveCallingLeads([]);
      }

      const response = await clientApi.get(`/api/campaigns/${id}/leads`, {
        params: {
          limit: leadsLimit,
          offset: leadsOffset,
          status: leadsStatusFilter || undefined,
          search: leadsSearch || undefined,
          outcome: leadsOutcomeFilter || undefined,
        },
      });

      const callingIds = new Set(nextCalling.map((l) => l.id));

      if (response.data) {
        const pageLeads = response.data.leads || [];
        // Page body excludes calling — those always come from the pinned live set
        const rest = pageLeads.filter((l) => l.status !== 'calling' && !callingIds.has(l.id));
        setLeads(rest);
        setTotalLeadsCount(response.data.total_count || 0);
      } else {
        setLeads([]);
      }
    } catch (err) {
      console.warn('API error listing leads', err);
      // Do NOT clear liveCallingLeads here — concurrent calls must remain visible
      setLeads([]);
    } finally {
      if (showSpinner) setLeadsLoading(false);
    }
  }, [
    id,
    leadsLimit,
    leadsOffset,
    leadsStatusFilter,
    leadsSearch,
    leadsOutcomeFilter,
    campaign?.status,
    campaign?.calling_leads,
  ]);

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

  useEffect(() => {
    if (!id) return;
    const loadOutcomes = async () => {
      try {
        const response = await clientApi.get(`/api/campaigns/${id}/outcomes`);
        setOutcomes(response.data?.outcomes || []);
      } catch (err) {
        console.error('Failed to load outcomes', err);
      }
    };

    loadOutcomes();
  }, [id]);

  useEffect(() => {
    setLeadsOffset(0);
  }, [leadsOutcomeFilter, leadsStatusFilter, leadsAttemptsFilter, leadsTurnsFilter, leadsSearch, leadsLimit]);

  const turnsIndex = useMemo(
    () => buildTurnsByLead((dashboardCalls || []).filter((c) => String(c.campaign_id) === String(id))),
    [dashboardCalls, id],
  );

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

    const pollInterval = isPausing ? 2000 : 5000;
    const interval = setInterval(() => {
      loadCampaignDetails(false);
    }, pollInterval);
    return () => clearInterval(interval);
  }, [campaign, loadCampaignDetails]);

  // Poll leads table while campaign is active
  useEffect(() => {
    if (!campaign || activeTab !== 'leads') return;
    const isPausing = campaign.status === 'pausing' || (campaign.status === 'paused' && campaign.calling_leads > 0);
    if (campaign.status !== 'running' && !isPausing) return;

    // Poll faster when there are live calls so the stacking order updates in real-time
    const hasLiveCalls = (campaign.calling_leads || 0) > 0 || liveCallingLeads.length > 0;
    const interval = setInterval(() => {
      loadLeads(false);
    }, hasLiveCalls ? 1500 : 5000);
    return () => clearInterval(interval);
  }, [campaign, activeTab, loadLeads, liveCallingLeads.length]);

  const handleOpenTranscript = (lead) => {
    setSelectedLeadForTranscript(lead);
    setIsTranscriptOpen(true);
  };

  // Frontend filtering for attempts / turns (status + outcome filtered server-side).
  // Live calling leads are NEVER filtered out — they stay pinned on top.
  const getFilteredLeads = () => {
    const callingIds = new Set(liveCallingLeads.map((l) => l.id));
    let filtered = leads.filter((l) => l.status !== 'calling' && !callingIds.has(l.id));

    if (leadsAttemptsFilter) {
      filtered = filtered.filter((l) => {
        const attempts = l.attempts || 0;
        if (leadsAttemptsFilter === '1') return attempts === 1;
        if (leadsAttemptsFilter === '2') return attempts === 2;
        if (leadsAttemptsFilter === '3') return attempts === 3;
        if (leadsAttemptsFilter === '4+') return attempts >= 4;
        return true;
      });
    }

    if (leadsTurnsFilter) {
      filtered = filtered.filter((l) => {
        const turns = getLeadTurns(l, turnsIndex);
        if (leadsTurnsFilter === '0') return turns === 0;
        if (leadsTurnsFilter === '1-3') return turns >= 1 && turns <= 3;
        if (leadsTurnsFilter === '4-8') return turns >= 4 && turns <= 8;
        if (leadsTurnsFilter === '9+') return turns >= 9;
        return true;
      });
    }

    return filtered;
  };

  const filteredLeads = getFilteredLeads();

  const isLiveDialing =
    campaign?.status === 'running' ||
    campaign?.status === 'pausing' ||
    (campaign?.status === 'paused' && ((campaign?.calling_leads || 0) > 0 || liveCallingLeads.length > 0));

  // Always pin live concurrent calls above everything else
  const sortedLeads = useMemo(() => {
    const pinned = sortLeadsCallStack(liveCallingLeads, { live: true });
    const rest = sortLeadsCallStack(filteredLeads, { live: isLiveDialing });
    const pinnedIds = new Set(pinned.map((l) => l.id));
    return [...pinned, ...rest.filter((l) => !pinnedIds.has(l.id))];
  }, [liveCallingLeads, filteredLeads, isLiveDialing]);

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

  const handleConfirmReleaseStuck = async () => {
    setIsReleasingStuck(true);
    try {
      const response = await clientApi.post(`/api/campaigns/${id}/release-stuck-calling`);
      const released = response.data?.released ?? 0;
      showToast(
        released > 0
          ? `Released ${released} stuck lead${released === 1 ? '' : 's'} back to callback scheduled.`
          : 'No stuck leads needed releasing.',
        released > 0 ? 'success' : 'info'
      );
      setIsReleaseStuckOpen(false);
      loadCampaignDetails();
      loadLeads(false);
    } catch (err) {
      console.warn('Release stuck leads failed.', err);
      showToast(err.customErrorMessage || 'Failed to release stuck leads.', 'error');
    } finally {
      setIsReleasingStuck(false);
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

  const handleDownloadTemplate = async () => {
    try {
      const response = await clientApi.get(`/api/campaigns/${id}/leads/template`, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `template.csv`);
      document.body.appendChild(link);
      link.click();
      link.parentNode.removeChild(link);
    } catch (err) {
      console.warn('Failed to download template', err);
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

  const handleAddLead = async (e) => {
    e?.preventDefault?.();
    if (!newLead.phone.trim()) return;

    try {
      const payload = {
        ...newLead,
        metadata: buildMetadataFromCustomFields(newLead.metadata, addLeadCustomColumns),
      };
      const response = await clientApi.post(`/api/campaigns/${id}/leads`, payload);
      if (response.data) {

        showToast('Lead added successfully.', 'success');
        setIsAddLeadOpen(false);
        setNewLead({ name: '', phone: '', lead_type: 'cold', metadata: {} });
        setAddLeadCustomColumns([]);
        loadLeads();
        loadCampaignDetails();
        return;
      }
    } catch (err) {
      console.warn('Manual lead add endpoint failed.', err);
      showToast(err.customErrorMessage || 'Failed to add lead. Please try again.', 'error');
    }
  };

  const handleEditLead = async (e) => {
    e?.preventDefault?.();
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

  const handleExport = async () => {
    try {
      const response = await clientApi.get(
        `/api/campaigns/${id}/leads/export`,
        {
          params: {
            search: leadsSearch || undefined,
            status: leadsStatusFilter || undefined,
            outcome: leadsOutcomeFilter || undefined,
            attempts: leadsAttemptsFilter || undefined,
          },
          responseType: "blob",
        }
      );

      const url = window.URL.createObjectURL(new Blob([response.data]));

      const link = document.createElement("a");
      link.href = url;
      link.download = `${campaign.name}-leads.xlsx`;

      document.body.appendChild(link);
      link.click();

      link.remove();
      window.URL.revokeObjectURL(url);

      showToast("Export completed successfully.", "success");
    } catch (err) {
      console.error(err);
      showToast(
        err.customErrorMessage || "Failed to export leads.",
        "error"
      );
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
  const pendingPercent = total > 0 ? ((campaign.pending_leads || 0) / total) * 100 : 0;
  const callingDisplay = liveCallingCount;
  const callingPercent = total > 0 ? (callingDisplay / total) * 100 : 0;
  const callbackPercent = total > 0 ? ((campaign.callback_leads || 0) / total) * 100 : 0;
  const completedPercent = total > 0 ? ((campaign.completed_leads || 0) / total) * 100 : 0;
  const failedPercent = total > 0 ? ((campaign.failed_leads || 0) / total) * 100 : 0;

  const renderKpiCard = (title, value, secondaryText, progressPercent, colorClass, iconName) => {
    const isBlue = colorClass.includes('blue');
    const isGreen = colorClass.includes('green');
    const isRed = colorClass.includes('red');
    const isPurple = colorClass.includes('purple');
    const isOrange = colorClass.includes('orange');
    const isYellow = colorClass.includes('yellow');

    let barColor = '#94A3B8';
    if (isBlue) barColor = '#2563EB';
    else if (isGreen) barColor = '#16A34A';
    else if (isRed) barColor = '#DC2626';
    else if (isPurple) barColor = '#7C3AED';
    else if (isOrange) barColor = '#EA580C';
    else if (isYellow) barColor = '#CA8A04';

    return (
      <div className="cl-kpi-card cl-kpi-card--compact animate-fade-in">
        <div className="cl-kpi-card__header">
          <span className="cl-kpi-card__label">{title}</span>
          <div className={`cl-kpi-card__icon ${colorClass}`}>
            <span className="material-symbols-outlined">{iconName}</span>
          </div>
        </div>
        <div className="cl-kpi-card__value">{value}</div>
        <div className="cl-kpi-card__footer">
          <div className="cl-kpi-card__secondary">{secondaryText}</div>
          <div className="cl-kpi-chart-footer">
            <div className="cl-kpi-progress">
              <div className="cl-kpi-progress-bar" style={{ width: `${Math.min(100, Math.max(0, progressPercent))}%`, background: barColor }} />
            </div>
            <span className="cl-kpi-card__meta">Real-time</span>
          </div>
        </div>
      </div>
    );
  };

  const renderStatusBadges = (lead) => {
    const status = lead.status;
    if (status === 'calling') {
      return <span className="cl-badge cl-badge--live">Live</span>;
    } else if (status === 'callback_scheduled') {
      return <span className="cl-badge cl-badge--callback">Callback Due</span>;
    } else if (status === 'completed') {
      return <span className="cl-badge cl-badge--completed">Completed</span>;
    } else if (status === 'failed') {
      return <span className="cl-badge cl-badge--failed">Failed</span>;
    } else if (status === 'pending') {
      return <span className="cl-badge cl-badge--queued">Pending</span>;
    } else {
      return <span className="cl-badge cl-badge--queued">{status || 'Unknown'}</span>;
    }
  };

  const totalPages = Math.max(1, Math.ceil(totalLeadsCount / leadsLimit));
  const currentPage = Math.floor(leadsOffset / leadsLimit) + 1;
  const hasClientFilters = Boolean(leadsAttemptsFilter || leadsTurnsFilter);
  const rangeStart = totalLeadsCount === 0 ? 0 : leadsOffset + 1;
  const rangeEnd = Math.min(leadsOffset + sortedLeads.length, totalLeadsCount);

  return (
    <>
      <div className="cl-page-container cl-campaign-detail">
        {isPausing && (
          <div className="cl-campaign-alert animate-fade-in">
            <div className="cl-campaign-alert__icon">
              <span className="material-symbols-outlined">hourglass_empty</span>
            </div>
            <div>
              <div className="cl-campaign-alert__title">Campaign is pausing…</div>
              <div className="cl-campaign-alert__text">
                Waiting for {campaign.calling_leads} active call{campaign.calling_leads !== 1 ? 's' : ''} to finish.
                If leads appear permanently stuck, use <strong>Release stuck leads</strong> below.
              </div>
            </div>
          </div>
        )}

        <div className="cl-campaign-header animate-fade-in">
          <div className="cl-campaign-header__info">
            <h1 className="cl-campaign-header__name">{campaign.name}</h1>
            <div className="cl-campaign-header__meta">
              <div className="cl-campaign-header__meta-item">
                <span className="material-symbols-outlined">tag</span>
                <span>Campaign ID: <span className="font-mono font-semibold">{campaign.id}</span></span>
              </div>
              <div className="cl-campaign-header__meta-item">
                <span className="material-symbols-outlined">calendar_today</span>
                <span>Created: {campaign.created_at ? new Date(campaign.created_at).toLocaleDateString() : 'N/A'}</span>
              </div>
              <div className="cl-campaign-header__meta-item">
                <span className="material-symbols-outlined">bolt</span>
                <span>Status: <span className={`cl-badge ${campaign.status === 'running' ? 'cl-badge--running' :
                  campaign.status === 'paused' ? 'cl-badge--paused' :
                    campaign.status === 'pausing' ? 'cl-badge--paused' :
                      campaign.status === 'completed' ? 'cl-badge--completed' :
                        campaign.status === 'cancelled' ? 'cl-badge--cancelled' :
                          'cl-badge--draft'
                  }`}>{campaign.status}</span></span>
              </div>
            </div>
          </div>

          <div className="cl-campaign-header__actions">
            {campaign.status !== 'cancelled' && campaign.status !== 'completed' && (
              <button
                onClick={handleToggleState}
                className={`cl-btn cl-btn--sm ${campaign.status === 'running' ? 'cl-btn--secondary' : 'cl-btn--primary'}`}
              >
                {campaign.status === 'running' ? (
                  <span className="material-symbols-outlined">pause</span>
                ) : null}
                {campaign.status === 'running' ? 'Pause Campaign' : 'Start Campaign'}
              </button>
            )}
            {campaign.calling_leads > 0 && ['running', 'pausing', 'paused'].includes(campaign.status) && (
              <button
                onClick={() => setIsReleaseStuckOpen(true)}
                disabled={isReleasingStuck}
                className="cl-btn cl-btn--secondary cl-btn--sm"
              >
                <span className="material-symbols-outlined">lock_open</span>
                Release stuck leads
              </button>
            )}
            {campaign.status === 'paused' && (
              <button
                onClick={handleCancelCampaign}
                className="cl-btn cl-btn--danger-outline cl-btn--sm"
              >
                <span className="material-symbols-outlined">cancel</span>
                Cancel &amp; Refund
              </button>
            )}
          </div>
        </div>

        <section className="campaign-kpi-section campaign-kpi-section--compact">
          <div className="campaign-kpi-section__head">
            <div className="campaign-kpi-grid">
              {renderKpiCard('Total Leads', total.toLocaleString(), `${(campaign.completed_leads || 0).toLocaleString()} completed`, total > 0 ? ((campaign.completed_leads || 0) / total) * 100 : 0, 'icon-blue', 'groups')}
              {renderKpiCard('Interested', (campaign.interested_leads || 0).toLocaleString(), `${total > 0 ? ((campaign.interested_leads || 0) / total * 100).toFixed(1) : 0}% conversion`, total > 0 ? ((campaign.interested_leads || 0) / total) * 100 : 0, 'icon-green', 'thumb_up')}
              {renderKpiCard('On Call', liveCallingCount.toLocaleString(), liveCallingCount > 0 ? 'Active right now' : 'Idle', total > 0 ? (liveCallingCount / total) * 100 : 0, 'icon-purple', 'ring_volume')}
              {renderKpiCard('Answered', (campaign.answered_leads || 0).toLocaleString(), `${total > 0 ? ((campaign.answered_leads || 0) / total * 100).toFixed(1) : 0}% answer rate`, total > 0 ? ((campaign.answered_leads || 0) / total) * 100 : 0, 'icon-teal', 'call')}
              {renderKpiCard('Pending', (campaign.pending_leads || 0).toLocaleString(), `${total > 0 ? ((campaign.pending_leads || 0) / total * 100).toFixed(1) : 0}% remaining`, total > 0 ? ((campaign.pending_leads || 0) / total) * 100 : 0, 'icon-orange', 'pending')}
            </div>
            <button
              type="button"
              onClick={() => setShowMoreStats(s => !s)}
              className="cl-btn cl-btn--secondary cl-btn--sm campaign-kpi-section__more"
            >
              <span className="material-symbols-outlined" style={{ fontSize: '14px' }}>
                {showMoreStats ? 'expand_less' : 'expand_more'}
              </span>
              {showMoreStats ? 'Hide stats' : 'See more stats'}
            </button>
          </div>

          {showMoreStats && (
            <div className="campaign-kpi-grid campaign-kpi-grid--secondary animate-fade-in">
              {renderKpiCard('Not Answered', (campaign.no_answer_leads || 0).toLocaleString(), `${total > 0 ? ((campaign.no_answer_leads || 0) / total * 100).toFixed(1) : 0}% rate`, total > 0 ? ((campaign.no_answer_leads || 0) / total) * 100 : 0, 'icon-orange', 'call_missed')}
              {renderKpiCard('Failed', (campaign.failed_leads || 0).toLocaleString(), `${total > 0 ? ((campaign.failed_leads || 0) / total * 100).toFixed(1) : 0}% rate`, total > 0 ? ((campaign.failed_leads || 0) / total) * 100 : 0, 'icon-red', 'cancel')}
              {renderKpiCard('Callback', (campaign.callback_leads || 0).toLocaleString(), `${total > 0 ? ((campaign.callback_leads || 0) / total * 100).toFixed(1) : 0}% scheduled`, total > 0 ? ((campaign.callback_leads || 0) / total) * 100 : 0, 'icon-blue', 'event_available')}
              {renderKpiCard('Completed', (campaign.completed_leads || 0).toLocaleString(), `${total > 0 ? ((campaign.completed_leads || 0) / total * 100).toFixed(1) : 0}% done`, total > 0 ? ((campaign.completed_leads || 0) / total) * 100 : 0, 'icon-green', 'task_alt')}
              {renderKpiCard('Budget Used', `₹${(campaign.budget_used_credits || 0).toLocaleString()}`, `of ₹${(campaign.budget_credits || 0).toLocaleString()} allocated`, campaign.budget_credits > 0 ? ((campaign.budget_used_credits || 0) / campaign.budget_credits) * 100 : 0, 'icon-purple', 'monetization_on')}
            </div>
          )}
        </section>

        <section className="cl-leads-module">
          <div className="cl-tabs">
            <button
              onClick={() => setActiveTab('leads')}
              className={`cl-tab ${activeTab === 'leads' ? 'active' : ''}`}
            >
              Leads
            </button>
            <button
              onClick={() => setActiveTab('overview')}
              className={`cl-tab ${activeTab === 'overview' ? 'active' : ''}`}
            >
              Overview
            </button>
          </div>

          {activeTab === 'overview' && (
            <div className="cl-overview-grid animate-fade-in">
              <div className="cl-card flex flex-col gap-4 p-6">
                <h3 className="cl-card-title border-b border-slate-200 pb-3">Resource Allocation</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <div className="text-xs text-muted font-medium">Total Budget Allocated</div>
                    <div className="text-sm font-semibold text-primary mt-1">{campaign.budget_credits} credits</div>
                  </div>
                  <div>
                    <div className="text-xs text-muted font-medium">Budget Spent</div>
                    <div className="text-sm font-semibold text-red-600 mt-1">{campaign.budget_used_credits || 0} credits</div>
                  </div>
                  <div>
                    <div className="text-xs text-muted font-medium">Max Concurrency</div>
                    <div className="text-sm font-semibold text-primary mt-1">{campaign.max_concurrent_calls} channels</div>
                  </div>
                  <div>
                    <div className="text-xs text-muted font-medium">Calls per Minute</div>
                    <div className="text-sm font-semibold text-primary mt-1">{campaign.calls_per_minute || 10} calls</div>
                  </div>
                </div>
              </div>

              <div className="cl-card flex flex-col gap-4 p-6">
                <h3 className="cl-card-title border-b border-slate-200 pb-3">Bot Configuration</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <div className="text-xs text-muted font-medium">AI Agent Persona</div>
                    <div className="text-sm font-semibold text-primary mt-1">{campaign.bot_config?.name || 'Assigned Bot'}</div>
                  </div>
                  <div>
                    <div className="text-xs text-muted font-medium">Pricing Rate</div>
                    <div className="text-sm font-semibold text-primary mt-1">{campaign.bot_config?.credits_per_minute || 1} credits/min</div>
                  </div>
                  <div>
                    <div className="text-xs text-muted font-medium">Max Call Attempts</div>
                    <div className="text-sm font-semibold text-primary mt-1">{campaign.max_attempts} attempts</div>
                  </div>
                  <div>
                    <div className="text-xs text-muted font-medium">Retry Delay</div>
                    <div className="text-sm font-semibold text-primary mt-1">{campaign.retry_delay_minutes} minutes</div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'leads' && (
            <div className="cl-leads-panel">
                <div className="cl-leads-toolbar">
                  <div className="flex flex-nowrap gap-3 items-center min-w-max">
                    <div className="cl-search-wrap flex-shrink-0" style={{ flex: '0 0 220px', maxWidth: '320px' }}>
                      <span className="material-symbols-outlined cl-search-icon">search</span>
                      <input
                        type="text"
                        className="cl-search"
                        placeholder="Search leads..."
                        value={leadsSearch}
                        onChange={(e) => setLeadsSearch(e.target.value)}
                      />
                    </div>
                    <div className="flex flex-nowrap gap-2 items-center flex-shrink-0 ml-auto">
                      {(leadsOutcomeFilter || leadsStatusFilter || leadsAttemptsFilter || leadsTurnsFilter) && (
                        <button
                          onClick={() => {
                            setLeadsOutcomeFilter('');
                            setLeadsStatusFilter('');
                            setLeadsAttemptsFilter('');
                            setLeadsTurnsFilter('');
                          }}
                          className="cl-btn cl-btn--secondary cl-btn--sm"
                          title="Reset filters"
                        >
                          <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>close</span>
                          Reset
                        </button>
                      )}

                      {
                        <>
                          {(campaign.status === 'draft' || campaign.status === 'paused') && (
                            <>
                              <input
                                type="file"
                                ref={fileInputRef}
                                onChange={handleFileBrowse}
                                className="hidden"
                                accept=".csv,.xlsx"
                              />

                              <button
                                onClick={() => fileInputRef.current?.click()}
                                className="cl-btn cl-btn--secondary cl-btn--sm"
                                title="Import CSV"
                              >
                                <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>
                                  upload_file
                                </span>
                                {isUploading ? 'Uploading...' : 'Import'}
                              </button>

                              <button
                                onClick={handleDownloadTemplate}
                                className="cl-btn cl-btn--secondary cl-btn--sm"
                                title="Download template"
                              >
                                <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>
                                  download
                                </span>
                                Template
                              </button>

                              <button
                                onClick={() => setIsAddLeadOpen(true)}
                                className="cl-btn cl-btn--primary cl-btn--sm"
                              >
                                <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>
                                  person_add
                                </span>
                                Add Lead
                              </button>
                            </>
                          )}

                          <button
                            onClick={handleExport}
                            className="cl-btn cl-btn--secondary cl-btn--sm"
                            title="Export Leads"
                          >
                            <span
                              className="material-symbols-outlined"
                              style={{ fontSize: "16px" }}
                            >
                              download
                            </span>
                            Export
                          </button>
                        </>
                      }
                    </div>
                  </div>
                </div>

                <div className="cl-leads-table-wrap">
                  <table className="cl-lead-table cl-lead-table--dense">
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Phone</th>
                        <th>
                          <div className="cl-th-filter">
                            <span>Status</span>
                            <select
                              value={leadsStatusFilter}
                              onChange={(e) => setLeadsStatusFilter(e.target.value)}
                              className="cl-th-filter__select"
                              aria-label="Filter by status"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <option value="">All</option>
                              <option value="pending">Pending</option>
                              <option value="calling">Calling</option>
                              <option value="callback_scheduled">Callback Due</option>
                              <option value="completed">Completed</option>
                              <option value="failed">Failed</option>
                            </select>
                          </div>
                        </th>
                        <th>
                          <div className="cl-th-filter">
                            <span>Outcome</span>
                            <select
                              value={leadsOutcomeFilter}
                              onChange={(e) => setLeadsOutcomeFilter(e.target.value)}
                              className="cl-th-filter__select"
                              aria-label="Filter by outcome"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <option value="">All</option>
                              {outcomes.map((outcome) => (
                                <option key={outcome} value={outcome}>
                                  {friendlyOutcome(outcome)}
                                </option>
                              ))}
                            </select>
                          </div>
                        </th>
                        <th>
                          <div className="cl-th-filter">
                            <span>Turns</span>
                            <select
                              value={leadsTurnsFilter}
                              onChange={(e) => setLeadsTurnsFilter(e.target.value)}
                              className="cl-th-filter__select"
                              aria-label="Filter by turns"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <option value="">All</option>
                              <option value="0">0</option>
                              <option value="1-3">1–3</option>
                              <option value="4-8">4–8</option>
                              <option value="9+">9+</option>
                            </select>
                          </div>
                        </th>
                        <th>
                          <div className="cl-th-filter">
                            <span>Attempts</span>
                            <select
                              value={leadsAttemptsFilter}
                              onChange={(e) => setLeadsAttemptsFilter(e.target.value)}
                              className="cl-th-filter__select"
                              aria-label="Filter by attempts"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <option value="">All</option>
                              <option value="1">1</option>
                              <option value="2">2</option>
                              <option value="3">3</option>
                              <option value="4+">4+</option>
                            </select>
                          </div>
                        </th>
                        <th className="text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {leadsLoading && sortedLeads.length === 0 ? (
                        <tr>
                          <td colSpan="7" className="text-center text-muted">Loading leads...</td>
                        </tr>
                      ) : sortedLeads.length === 0 ? (
                        <tr>
                          <td colSpan="7" className="text-center py-8">No leads found.</td>
                        </tr>
                      ) : (
                        sortedLeads.map((lead) => (
                          <tr
                            key={lead.id}
                            className={lead.status === 'calling' ? 'cl-lead--live' : ''}
                            onClick={() => handleOpenTranscript(lead)}
                          >
                            <td className="font-semibold text-primary">{lead.name || '—'}</td>
                            <td className="font-mono">{lead.phone}</td>
                            <td>{renderStatusBadges(lead)}</td>
                            <td>
                              {lead.outcome ? (
                                <span className={`cl-badge ${lead.outcome === 'Interested' ? 'cl-badge--interested' :
                                  lead.outcome === 'Not_Interested' ? 'cl-badge--not_interested' :
                                    lead.outcome === 'Callback_Requested' ? 'cl-badge--callback' :
                                      lead.outcome === 'No_Answer' ? 'cl-badge--queued' :
                                        lead.outcome === 'Busy' ? 'cl-badge--busy' :
                                          lead.outcome === 'Early_Disconnect' ? 'cl-badge--paused' :
                                            'cl-badge--queued'
                                  }`}>
                                  {friendlyOutcome(lead.outcome)}
                                </span>
                              ) : (
                                <span style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>—</span>
                              )}
                            </td>
                            <td>{getLeadTurns(lead, turnsIndex)}</td>
                            <td>{lead.attempts || 0}</td>
                            <td className="text-right" onClick={(e) => e.stopPropagation()}>
                              <div className="flex justify-end gap-2.5 flex-wrap">
                                <button
                                  className="cl-btn cl-btn--secondary cl-btn--icon cl-btn--sm"
                                  onClick={() => {
                                    setEditLeadData({ ...lead, original_status: lead.status });
                                    setIsEditLeadOpen(true);
                                  }}
                                  title="Edit Lead"
                                >
                                  <span className="material-symbols-outlined text-[18px]">edit</span>
                                </button>
                                <button
                                  className="cl-btn cl-btn--secondary cl-btn--icon cl-btn--sm text-red-600"
                                  onClick={() => handleDeleteLead(lead.id)}
                                  title="Delete Lead"
                                >
                                  <span className="material-symbols-outlined text-[18px]">delete</span>
                                </button>
                                <button
                                  className="cl-btn cl-btn--primary cl-btn--sm"
                                  onClick={() => handleOpenTranscript(lead)}
                                >
                                  Details
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>

                <div className="cl-leads-footer">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="text-xs text-muted">
                      {hasClientFilters ? (
                        <>
                          {sortedLeads.length} match{sortedLeads.length === 1 ? '' : 'es'} on this page
                          <span> (of {totalLeadsCount.toLocaleString()} total)</span>
                        </>
                      ) : (
                        <>
                          Showing {rangeStart.toLocaleString()}–{rangeEnd.toLocaleString()} of {totalLeadsCount.toLocaleString()} leads
                        </>
                      )}
                    </span>
                    <label className="flex items-center gap-2 text-xs text-muted">
                      Per page
                      <select
                        value={leadsLimit}
                        onChange={(e) => setLeadsLimit(Number(e.target.value))}
                        className="cl-select cl-btn--sm"
                        style={{ minWidth: '72px', padding: '4px 8px' }}
                      >
                        <option value={5}>5</option>
                        <option value={10}>10</option>
                        <option value={25}>25</option>
                        <option value={50}>50</option>
                        <option value={100}>100</option>
                      </select>
                    </label>
                  </div>
                  <div className="flex gap-2 items-center">
                    <span className="text-xs text-muted">
                      Page {currentPage} of {totalPages}
                    </span>
                    <button
                      disabled={leadsOffset === 0}
                      onClick={() => setLeadsOffset(prev => Math.max(0, prev - leadsLimit))}
                      className="cl-btn cl-btn--secondary cl-btn--sm"
                    >
                      Prev
                    </button>
                    <button
                      disabled={leadsOffset + leadsLimit >= totalLeadsCount}
                      onClick={() => setLeadsOffset(prev => prev + leadsLimit)}
                      className="cl-btn cl-btn--secondary cl-btn--sm"
                    >
                      Next
                    </button>
                  </div>
                </div>
            </div>
          )}

          {/* Tab 3: Settings Content */}
          {activeTab === 'settings' && (
            <form onSubmit={handleSaveSettings} className="space-y-6 animate-fade-in max-w-xl p-6">
              <h3 className="text-lg font-semibold text-primary border-b border-slate-200 pb-3">Campaign Settings</h3>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-bold text-on-surface dark:text-molten-text mb-1">Campaign Objective Name</label>
                  <input
                    type="text"
                    className="cl-input rounded-xl"
                    value={campaign.name}
                    onChange={(e) => setCampaign({ ...campaign, name: e.target.value })}
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-bold text-on-surface dark:text-molten-text mb-1">Max Concurrent Call channels</label>
                  <input
                    type="number"
                    className="cl-input rounded-xl"
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
                      className="cl-input rounded-xl"
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
                      className="cl-input rounded-xl"
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
                className="cl-btn cl-btn--primary h-11 rounded-xl"
              >
                Save Settings
              </button>
            </form>
          )}
        </section>
      </div>

      <Modal
        open={isAddLeadOpen}
        onClose={() => {
          setIsAddLeadOpen(false);
          setAddLeadCustomColumns([]);
        }}
        title="Add New Lead"
        subtitle="Add a lead manually to start AI outreach instantly."
        icon="person_add"
        width={480}
        footer={(
          <>
            <Button variant="ghost" onClick={() => { setIsAddLeadOpen(false); setAddLeadCustomColumns([]); }}>Cancel</Button>
            <Button variant="primary" onClick={handleAddLead}>Add Contact</Button>
          </>
        )}
      >
        <form className="ent-form" onSubmit={handleAddLead}>
          <label>
            Full Name
            <input
              type="text"
              value={newLead.name}
              onChange={(e) => setNewLead({ ...newLead, name: e.target.value })}
              placeholder="e.g. Rahul Patil"
            />
          </label>

          <label>
            Phone Number (with prefix)
            <input
              type="tel"
              value={newLead.phone}
              onChange={(e) => setNewLead({ ...newLead, phone: e.target.value })}
              placeholder="e.g. +919988776655"
              required
            />
          </label>

          <label>
            Lead Type
            <select
              value={newLead.lead_type}
              onChange={(e) => setNewLead({ ...newLead, lead_type: e.target.value })}
            >
              <option value="cold">Cold</option>
              <option value="warm">Warm</option>
              <option value="hot">Hot</option>
            </select>
          </label>

          {getDynamicLeadFields()
            .filter((f) => f.key !== 'lead_name' && f.key !== 'lead_phone' && f.key !== 'name' && f.key !== 'phone')
            .map((field) => (
              <label key={field.key}>
                {field.key.replace(/_/g, ' ')}{field.required ? ' *' : ''}
                <input
                  type={field.type === 'number' ? 'number' : 'text'}
                  required={field.required}
                  value={newLead.metadata[field.key] || ''}
                  onChange={(e) => setNewLead({
                    ...newLead,
                    metadata: { ...newLead.metadata, [field.key]: e.target.value },
                  })}
                  placeholder={field.description || ''}
                />
              </label>
            ))}

          <CustomMetadataFields fields={addLeadCustomColumns} onChange={setAddLeadCustomColumns} />
        </form>
      </Modal>

      <Modal
        open={isEditLeadOpen && Boolean(editLeadData)}
        onClose={() => setIsEditLeadOpen(false)}
        title="Edit Lead"
        subtitle="Modify lead details and manual status settings."
        icon="edit"
        width={480}
        footer={(
          <>
            <Button variant="ghost" onClick={() => setIsEditLeadOpen(false)}>Cancel</Button>
            <Button variant="primary" onClick={(e) => handleEditLead(e)}>Save Changes</Button>
          </>
        )}
      >
        {editLeadData && (
          <form className="ent-form" onSubmit={handleEditLead}>
            <label>
              Full Name
              <input
                type="text"
                value={editLeadData.name || ''}
                onChange={(e) => setEditLeadData({ ...editLeadData, name: e.target.value })}
                placeholder="e.g. Rahul Patil"
              />
            </label>

            <label>
              Phone Number (with prefix)
              <input type="tel" value={editLeadData.phone} disabled />
            </label>

            <label>
              Lead Type
              <select
                value={editLeadData.lead_type || 'cold'}
                onChange={(e) => setEditLeadData({ ...editLeadData, lead_type: e.target.value })}
              >
                <option value="cold">Cold</option>
                <option value="warm">Warm</option>
                <option value="hot">Hot</option>
              </select>
            </label>

            {getDynamicLeadFields()
              .filter((f) => f.key !== 'lead_name' && f.key !== 'lead_phone' && f.key !== 'name' && f.key !== 'phone')
              .map((field) => (
                <label key={field.key}>
                  {field.key.replace(/_/g, ' ')}{field.required ? ' *' : ''}
                  <input
                    type={field.type === 'number' ? 'number' : 'text'}
                    required={field.required}
                    value={editLeadData.metadata?.[field.key] || ''}
                    onChange={(e) => setEditLeadData({
                      ...editLeadData,
                      metadata: { ...(editLeadData.metadata || {}), [field.key]: e.target.value },
                    })}
                    placeholder={field.description || ''}
                  />
                </label>
              ))}

            <label>
              Status
              <select
                value={editLeadData.status || 'pending'}
                onChange={(e) => setEditLeadData({ ...editLeadData, status: e.target.value })}
              >
                {(() => {
                  let allowed = {
                    pending: ['pending', 'failed', 'callback_scheduled', 'completed'],
                    callback_scheduled: ['callback_scheduled', 'pending', 'failed', 'completed'],
                    failed: ['failed', 'pending', 'completed'],
                    completed: ['completed', 'pending'],
                    calling: ['calling'],
                  }[editLeadData.original_status] || [editLeadData.original_status];

                  const attempts = editLeadData.attempts || 0;
                  const maxAttempts = editLeadData.max_attempts || 3;
                  if (attempts >= maxAttempts) {
                    allowed = allowed.filter((s) => s !== 'callback_scheduled');
                  }

                  return [
                    { value: 'pending', label: 'Pending / Retry' },
                    { value: 'failed', label: 'Failed' },
                    { value: 'completed', label: 'Completed' },
                    { value: 'callback_scheduled', label: 'Callback Scheduled' },
                  ].map((opt) => (
                    <option
                      key={opt.value}
                      value={opt.value}
                      disabled={!allowed.includes(opt.value)}
                    >
                      {opt.label}
                    </option>
                  ));
                })()}
                {editLeadData.original_status === 'calling' && (
                  <option value="calling" disabled>Calling (In Progress)</option>
                )}
              </select>
            </label>
            {editLeadData.status !== editLeadData.original_status && (
              <p className="ent-form__hint">Status change may require confirmation.</p>
            )}
          </form>
        )}
      </Modal>

      <Modal
        open={isStartConfirmOpen}
        onClose={() => setIsStartConfirmOpen(false)}
        title="Start Outbound Dialer"
        subtitle={campaign ? `Campaign: ${campaign.name}` : undefined}
        icon="play_circle"
        width={480}
        footer={(
          <>
            <Button variant="ghost" onClick={() => setIsStartConfirmOpen(false)}>Cancel</Button>
            <Button variant="primary" onClick={handleConfirmStart}>Acknowledge &amp; Start</Button>
          </>
        )}
      >
        <div className="ent-form">
          <p className="ent-form__hint" style={{ margin: 0 }}>
            You are about to launch the outbound dialer queue. Please verify compliance before starting.
          </p>
          <div className={`ent-form__warn ${istStatus.isInside ? '' : ''}`} style={istStatus.isInside ? { background: '#ecfdf5', borderColor: '#a7f3d0', color: '#047857' } : undefined}>
            <strong>{istStatus.isInside ? 'Calling Hours Active' : 'Calling Hours Restricted'}</strong>
            <br />
            {istStatus.isInside
              ? `Outbound dialing is allowed. Current time is ${istStatus.formattedIst}.`
              : `Dialer is paused until 9 AM IST. Current time is ${istStatus.formattedIst}.`}
          </div>
        </div>
      </Modal>

      <Modal
        open={isReleaseStuckOpen}
        onClose={() => setIsReleaseStuckOpen(false)}
        title="Release stuck leads?"
        subtitle="Reset leads stuck in calling state back to pending."
        icon="warning"
        width={480}
        footer={(
          <>
            <Button variant="ghost" onClick={() => setIsReleaseStuckOpen(false)} disabled={isReleasingStuck}>Cancel</Button>
            <Button variant="primary" loading={isReleasingStuck} onClick={handleConfirmReleaseStuck}>
              Release stuck leads
            </Button>
          </>
        )}
      >
        <p className="ent-form__hint" style={{ margin: 0 }}>
          This resets leads stuck in &quot;Calling&quot; back to &quot;Pending&quot; so they can be redialed.
          Calls that are actively in progress will not be interrupted.
          {campaign && (
            <>
              {' '}Currently showing <strong>{campaign.calling_leads}</strong> lead{campaign.calling_leads === 1 ? '' : 's'} in calling state.
            </>
          )}
        </p>
      </Modal>



      <CallTranscriptDrawer
        isOpen={isTranscriptOpen}
        sessionCallId={selectedLeadForTranscript?.session_call_id || null}
        leadName={selectedLeadForTranscript ? selectedLeadForTranscript.name : ''}
        leadData={selectedLeadForTranscript}
        onClose={() => setIsTranscriptOpen(false)}
      />

    </>
  );
};

export default CampaignDetail;
