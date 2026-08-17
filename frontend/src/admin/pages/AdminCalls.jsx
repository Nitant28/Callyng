import React, { useState, useEffect, useCallback } from 'react';
import adminApi from '../../shared/api/admin';
import { useAdminData } from '../contexts/AdminDataContext';

const formatInr = (n) =>
  `₹${Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;


export default function AdminCalls() {
  const { clientsMap } = useAdminData();
  const [calls, setCalls] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState('');
  
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  // Drawer state
  const [selectedCall, setSelectedCall] = useState(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [callData, setCallData] = useState(null);
  const [callLoading, setCallLoading] = useState(false);
  const [recordingUrl, setRecordingUrl] = useState(null);
  const [recordingLoading, setRecordingLoading] = useState(false);
  const [recordingError, setRecordingError] = useState(null);

  const fetchCalls = useCallback(async () => {
    setLoading(true);
    try {
      const response = await adminApi.get('/internal/calls', {
        params: { limit, offset, search: search || undefined }
      });
      setCalls(response.data.calls || []);
      setTotalCount(response.data.total_count || 0);
      setError(null);
    } catch (err) {
      console.error("Failed to fetch calls", err);
      setError(err.customErrorMessage || "Failed to load calls");
      setCalls([]);
    } finally {
      setLoading(false);
    }
  }, [limit, offset, search]);

  useEffect(() => {
    fetchCalls();
  }, [fetchCalls]);

  const handleOpenDrawer = async (call) => {
    setSelectedCall(call);
    setIsDrawerOpen(true);
    setCallLoading(true);
    setCallData(null);
    setRecordingUrl(null);
    setRecordingError(null);
    setRecordingLoading(false);
    
    try {
      const response = await adminApi.get(`/internal/calls/${call.session_call_id}`);
      if (response.data?.call) {
        setCallData(response.data.call);
      }
    } catch (err) {
      console.warn("API error fetching call transcript details", err);
    } finally {
      setCallLoading(false);
    }
  };

  const loadRecording = async (sessionCallId) => {
    if (!sessionCallId || recordingUrl || recordingLoading) return;
    setRecordingLoading(true);
    setRecordingError(null);
    try {
      const recResp = await adminApi.get(`/internal/calls/${sessionCallId}/recording`);
      setRecordingUrl(recResp.data.url);
    } catch (err) {
      setRecordingError(err.response?.data?.detail || "No recording available");
    } finally {
      setRecordingLoading(false);
    }
  };

  const handleForceStop = async (e, call_id) => {
    e.stopPropagation();
    if (window.confirm(`Are you sure you want to FORCE STOP call ${call_id}?`)) {
      // Not fully implemented on backend, placeholder for future
      alert("Force stop feature is WIP.");
    }
  };

  const renderStatus = (call) => {
    if (call.in_progress) {
      return (
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-arctic-error dark:bg-molten-error animate-pulse shadow-[0_0_8px_rgba(220,50,60,0.6)]"></div>
          <span className="font-label-md text-label-md text-arctic-error dark:text-molten-error">Live</span>
        </div>
      );
    }
    const status = call.outcome || 'Unknown';
    return (
      <div className="flex items-center gap-2">
        <div className="w-2 h-2 rounded-full bg-outline-variant"></div>
        <span className="font-label-md text-label-md text-on-surface-variant capitalize">{status.replace(/_/g, ' ')}</span>
      </div>
    );
  };

  const formatDuration = (sec) => {
    if (!sec && sec !== 0) return '-';
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}m ${s}s`;
  };

  const formatRelativeTime = (isoString) => {
    if (!isoString) return '-';
    const date = new Date(isoString);
    const diffInSeconds = Math.floor((new Date() - date) / 1000);
    if (diffInSeconds < 60) return `${diffInSeconds}s ago`;
    const diffInMinutes = Math.floor(diffInSeconds / 60);
    if (diffInMinutes < 60) return `${diffInMinutes}m ago`;
    const diffInHours = Math.floor(diffInMinutes / 60);
    if (diffInHours < 24) return `${diffInHours}h ago`;
    const diffInDays = Math.floor(diffInHours / 24);
    return `${diffInDays}d ago`;
  };

  return (
    <div className="w-full relative">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end mb-stack-lg gap-4">
        <div>
          <h2 className="font-headline-lg text-headline-lg text-on-surface dark:text-molten-text">Global Calls Feed</h2>
          <p className="font-body-md text-body-md text-arctic-text-muted dark:text-molten-text-muted mt-1">Real-time monitoring of outbound platform activity.</p>
        </div>
        <div className="flex gap-3 items-center">
          <input 
            type="text"
            placeholder="Search Call ID or Outcome"
            className="px-4 py-2 bg-surface-container-lowest dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] rounded-lg text-sm text-on-surface dark:text-molten-text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button onClick={fetchCalls} className="px-4 py-2 bg-surface-container-low dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-lg hover:bg-surface-container transition-colors material-symbols-outlined text-on-surface dark:text-molten-text">
            refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-4 bg-error-container text-on-error-container rounded-lg flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined">error</span>
            <span>{error}</span>
          </div>
          <button onClick={fetchCalls} className="text-sm underline hover:opacity-80">Retry</button>
        </div>
      )}

      {/* Data Table Card */}
      <div className="bg-surface-container-lowest dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse min-w-[800px]">
            <thead className="bg-surface-container-low dark:bg-[#1A1C24] border-b border-outline-variant dark:border-[#2A345E]">
              <tr>
                <th className="p-3 pl-4 font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted tracking-wider">Call ID</th>
                <th className="p-3 font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted tracking-wider">Client</th>
                <th className="p-3 font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted tracking-wider">Route</th>
                <th className="p-3 font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted tracking-wider text-right">Duration</th>
                <th className="p-3 font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted tracking-wider text-right">Cost</th>
                <th className="p-3 font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted tracking-wider">Started</th>
                <th className="p-3 font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted tracking-wider">Status</th>
                <th className="p-3 pr-4 font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted tracking-wider text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="font-body-sm text-body-sm text-on-surface dark:text-molten-text divide-y divide-outline-variant/50 dark:divide-[#2A345E]/50">
              {calls.map((call, idx) => (
                <tr key={call.session_call_id || idx} onClick={() => handleOpenDrawer(call)} className="hover:bg-surface-container/30 dark:hover:bg-molten-bg/50 transition-colors group cursor-pointer">
                  <td className="p-3 pl-4 tabular-nums text-arctic-text-muted dark:text-molten-text-muted font-mono text-xs" title={call.session_call_id}>
                    {call.session_call_id ? call.session_call_id.substring(0,8) : '-'}
                  </td>
                  <td className="p-3 font-medium">{clientsMap[call.client_id]?.name || 'Unknown Client'}</td>
                  <td className="p-3">
                    <span className={`px-2 py-1 text-xs rounded-full border ${call.route === 'sts' ? 'bg-primary/10 dark:bg-molten-primary/20 text-primary dark:text-molten-primary border-primary/20 dark:border-molten-primary/30' : 'bg-secondary/10 dark:bg-[#5cf7db]/20 text-secondary dark:text-[#5cf7db] border-secondary/20 dark:border-[#5cf7db]/30'}`}>
                      {call.route || 'unknown'}
                    </span>
                  </td>
                  <td className={`p-3 tabular-nums text-right ${call.in_progress ? 'font-medium' : 'text-arctic-text-muted dark:text-molten-text-muted'}`}>
                    {formatDuration(call.duration_seconds)}
                  </td>
                  <td className="p-3 tabular-nums text-right text-arctic-text-muted dark:text-molten-text-muted">
                    {call.credits_charged != null ? formatInr(call.credits_charged) : (call.in_progress ? '—' : formatInr(0))}
                  </td>
                  <td className="p-3 text-arctic-text-muted dark:text-molten-text-muted" title={call.started_at}>
                    {formatRelativeTime(call.started_at)}
                  </td>
                  <td className="p-3">
                    {renderStatus(call)}
                  </td>
                  <td className="p-3 pr-4 text-right">
                    {call.in_progress && (
                      <button 
                        className="btn-force-stop px-3 py-1 bg-error-container/20 dark:bg-molten-error/10 text-arctic-error dark:text-molten-error border border-arctic-error/30 dark:border-molten-error/30 rounded-full font-label-sm text-label-sm transition-all opacity-0 group-hover:opacity-100 flex items-center gap-1 ml-auto"
                        onClick={(e) => handleForceStop(e, call.session_call_id)}
                      >
                        <span className="material-symbols-outlined text-[14px]">stop_circle</span>
                        Force Stop
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {calls.length === 0 && !loading && !error && (
                <tr>
                  <td colSpan="8" className="p-8 text-center text-on-surface-variant">No calls found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        
        {/* Pagination */}
        <div className="p-4 border-t border-outline-variant dark:border-[#2A345E] flex justify-between items-center bg-surface-container-low dark:bg-[#1A1C24]">
          <span className="text-sm text-on-surface-variant">
            Showing {offset + 1} to {Math.min(offset + limit, totalCount)} of {totalCount} calls
          </span>
          <div className="flex gap-2 items-center">
            <select 
              value={limit} 
              onChange={e => { setLimit(Number(e.target.value)); setOffset(0); }}
              className="px-2 py-1 bg-surface-container dark:bg-molten-surface border border-outline-variant rounded text-sm text-on-surface"
            >
              <option value="25">25 / page</option>
              <option value="50">50 / page</option>
              <option value="100">100 / page</option>
            </select>
            <div className="flex gap-1">
              <button 
                disabled={offset === 0} 
                onClick={() => setOffset(Math.max(0, offset - limit))}
                className="p-1 rounded hover:bg-surface-container disabled:opacity-50 text-on-surface"
              >
                <span className="material-symbols-outlined">chevron_left</span>
              </button>
              <button 
                disabled={offset + limit >= totalCount} 
                onClick={() => setOffset(offset + limit)}
                className="p-1 rounded hover:bg-surface-container disabled:opacity-50 text-on-surface"
              >
                <span className="material-symbols-outlined">chevron_right</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Drawer Overlay */}
      {isDrawerOpen && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setIsDrawerOpen(false)}></div>
          <div className="relative w-full max-w-2xl bg-surface-container-lowest dark:bg-molten-bg h-full shadow-2xl flex flex-col transform transition-transform duration-300 translate-x-0 border-l border-outline-variant dark:border-molten-primary/20">
            {/* Header */}
            <div className="p-6 border-b border-outline-variant dark:border-molten-primary/20 flex justify-between items-center bg-surface-container-low dark:bg-molten-surface">
              <div>
                <h3 className="font-headline-sm text-on-background dark:text-molten-text">Call Details</h3>
                <p className="text-sm text-on-surface-variant font-mono mt-1">{selectedCall?.session_call_id}</p>
              </div>
              <button onClick={() => setIsDrawerOpen(false)} className="p-2 rounded-full hover:bg-surface-container-highest dark:hover:bg-[#2A345E] transition-colors text-on-surface dark:text-molten-text">
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            
            {/* Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-8">
              {callLoading ? (
                <div className="flex justify-center p-12"><span className="material-symbols-outlined animate-spin text-3xl text-primary">progress_activity</span></div>
              ) : callData ? (
                <>
                  {/* Metadata */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="p-3 bg-surface-container dark:bg-[#1A1C24] rounded-lg">
                      <div className="text-xs text-on-surface-variant dark:text-molten-text-muted mb-1">Status</div>
                      <div className="font-medium text-sm text-on-surface dark:text-molten-text">{callData.in_progress ? 'Live' : (callData.outcome || 'Unknown')}</div>
                    </div>
                    <div className="p-3 bg-surface-container dark:bg-[#1A1C24] rounded-lg">
                      <div className="text-xs text-on-surface-variant dark:text-molten-text-muted mb-1">Duration</div>
                      <div className="font-medium text-sm text-on-surface dark:text-molten-text">{formatDuration(callData.duration_seconds)}</div>
                    </div>
                    <div className="p-3 bg-surface-container dark:bg-[#1A1C24] rounded-lg">
                      <div className="text-xs text-on-surface-variant dark:text-molten-text-muted mb-1">Total</div>
                      <div className="font-medium text-sm text-on-surface dark:text-molten-text">{formatInr(callData.credits_charged)}</div>
                    </div>
                    <div className="p-3 bg-surface-container dark:bg-[#1A1C24] rounded-lg">
                      <div className="text-xs text-on-surface-variant dark:text-molten-text-muted mb-1">Telephony</div>
                      <div className="font-medium text-sm text-on-surface dark:text-molten-text">
                        {callData.setup_charge != null || callData.call_data?.setup_charge != null
                          ? formatInr(callData.setup_charge ?? callData.call_data.setup_charge)
                          : '—'}
                      </div>
                    </div>
                    <div className="p-3 bg-surface-container dark:bg-[#1A1C24] rounded-lg">
                      <div className="text-xs text-on-surface-variant dark:text-molten-text-muted mb-1">Bot</div>
                      <div className="font-medium text-sm text-on-surface dark:text-molten-text">
                        {callData.duration_charge != null || callData.call_data?.duration_charge != null
                          ? formatInr(callData.duration_charge ?? callData.call_data.duration_charge)
                          : '—'}
                      </div>
                    </div>
                  </div>

                  {callData.in_progress && (
                    <div className="p-3 bg-warning-container text-on-warning-container dark:bg-molten-warning/10 dark:text-molten-warning rounded-lg text-sm flex gap-2">
                      <span className="material-symbols-outlined text-[18px]">info</span>
                      Live transcript polling requires client API key. Admin view is static.
                    </div>
                  )}

                  {/* Recording */}
                  <div>
                    <h4 className="font-label-lg mb-4 text-on-background dark:text-molten-text">Call Recording</h4>
                    {recordingLoading ? (
                      <div className="flex items-center gap-2 text-sm text-on-surface-variant dark:text-molten-text-muted">
                        <span className="material-symbols-outlined animate-spin text-lg">progress_activity</span>
                        Loading recording...
                      </div>
                    ) : recordingUrl ? (
                      <div className="flex items-center gap-2">
                        <audio controls preload="none" src={recordingUrl} className="flex-1 h-10 outline-none" controlsList="nodownload" />
                        <a 
                          href={recordingUrl} 
                          download={`call_recording_${callData.session_call_id || 'lead'}.mp3`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center justify-center w-10 h-10 shrink-0 bg-surface-container dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] rounded-lg text-on-surface-variant dark:text-molten-text-muted hover:bg-outline-variant dark:hover:bg-[#2A345E]/50 transition-colors cursor-pointer group"
                          title="Download Recording"
                        >
                          <span className="material-symbols-outlined text-lg group-hover:text-primary dark:group-hover:text-molten-primary transition-colors">download</span>
                        </a>
                      </div>
                    ) : recordingError ? (
                      <div className="text-sm text-on-surface-variant dark:text-molten-text-muted italic bg-surface-container-lowest dark:bg-[#111] p-4 rounded-xl border border-outline-variant dark:border-[#2A345E]">
                        {recordingError}
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => loadRecording(callData.session_call_id || selectedCall?.session_call_id)}
                        className="text-sm px-4 py-2 rounded-lg border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text hover:bg-surface-container"
                      >
                        Load recording
                      </button>
                    )}
                  </div>

                  {/* Transcript */}
                  <div>
                    <h4 className="font-label-lg mb-4 text-on-background dark:text-molten-text">Transcript</h4>
                    <div className="space-y-3 bg-surface-container-lowest dark:bg-[#111] p-4 rounded-xl border border-outline-variant dark:border-[#2A345E]">
                      {callData.transcript && callData.transcript.length > 0 ? (
                        callData.transcript.map((msg, i) => (
                          <div key={i} className={`flex ${msg.role === 'assistant' ? 'justify-start' : 'justify-end'}`}>
                            <div className={`max-w-[85%] rounded-2xl p-3 text-sm ${
                              msg.role === 'assistant' 
                                ? 'bg-surface-container dark:bg-[#1A1C24] text-on-surface dark:text-molten-text rounded-tl-sm' 
                                : 'bg-primary text-on-primary rounded-tr-sm'
                            }`}>
                              {msg.content}
                            </div>
                          </div>
                        ))
                      ) : (
                        <p className="text-sm text-on-surface-variant dark:text-molten-text-muted italic">No transcript available.</p>
                      )}
                    </div>
                  </div>

                  {/* Extraction */}
                  <div>
                    <h4 className="font-label-lg mb-4 text-on-background dark:text-molten-text">AI Extraction</h4>
                    {callData.extraction_error && (
                      <div className="mb-4 p-3 bg-error-container text-on-error-container rounded-lg text-sm border border-error/20 font-mono">
                        {callData.extraction_error}
                      </div>
                    )}
                    <div className="bg-surface-container-lowest dark:bg-[#111] border border-outline-variant dark:border-[#2A345E] rounded-xl overflow-hidden">
                      {callData.extraction_json && Object.keys(callData.extraction_json).length > 0 ? (
                        <dl className="divide-y divide-outline-variant/50 dark:divide-[#2A345E]">
                          {Object.entries(callData.extraction_json).map(([k, v], i) => (
                            <div key={i} className="flex px-4 py-3">
                              <dt className="w-1/3 text-sm font-medium text-on-surface-variant dark:text-molten-text-muted">{k}</dt>
                              <dd className="w-2/3 text-sm text-on-surface dark:text-molten-text break-words">
                                {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                              </dd>
                            </div>
                          ))}
                        </dl>
                      ) : (
                        <div className="p-4 text-sm text-on-surface-variant dark:text-molten-text-muted italic">No data extracted.</div>
                      )}
                    </div>
                  </div>

                  {/* Usage Stats */}
                  <div>
                    <h4 className="font-label-lg mb-4 text-on-background dark:text-molten-text">Usage Stats</h4>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div className="p-3 bg-surface-container dark:bg-[#1A1C24] rounded-lg">
                        <div className="text-xs text-on-surface-variant dark:text-molten-text-muted mb-1">Prompt Tokens</div>
                        <div className="font-mono text-sm text-on-surface dark:text-molten-text">{callData.usage_prompt_tokens || 0}</div>
                      </div>
                      <div className="p-3 bg-surface-container dark:bg-[#1A1C24] rounded-lg">
                        <div className="text-xs text-on-surface-variant dark:text-molten-text-muted mb-1">Completion Tokens</div>
                        <div className="font-mono text-sm text-on-surface dark:text-molten-text">{callData.usage_completion_tokens || 0}</div>
                      </div>
                      <div className="p-3 bg-surface-container dark:bg-[#1A1C24] rounded-lg">
                        <div className="text-xs text-on-surface-variant dark:text-molten-text-muted mb-1">Total Tokens</div>
                        <div className="font-mono text-sm text-on-surface dark:text-molten-text">{callData.usage_total_tokens || 0}</div>
                      </div>
                      <div className="p-3 bg-surface-container dark:bg-[#1A1C24] rounded-lg">
                        <div className="text-xs text-on-surface-variant dark:text-molten-text-muted mb-1">TTS Chars</div>
                        <div className="font-mono text-sm text-on-surface dark:text-molten-text">{callData.usage_tts_characters || 0}</div>
                      </div>
                    </div>
                  </div>

                </>
              ) : (
                <div className="text-center text-on-surface-variant">Failed to load call details.</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
