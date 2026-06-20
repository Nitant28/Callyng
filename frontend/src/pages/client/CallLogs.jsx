import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useTheme } from '../../hooks/useTheme';
import clientApi from '../../api/client';
import LoaderOverlay from '../../components/shared/LoaderOverlay';

const CallLogs = () => {
  const { theme, toggleTheme } = useTheme();

  // Call logs state
  const [calls, setCalls] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [limit] = useState(10);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);

  // Drawer details state
  const [selectedCall, setSelectedCall] = useState(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [callData, setCallData] = useState(null);
  const [callLoading, setCallLoading] = useState(false);

  // Playback state
  const [isPlaying, setIsPlaying] = useState(false);
  const [playSeconds, setPlaySeconds] = useState(84); // Default starts at 01:24

  // Load calls list
  const loadCalls = useCallback(async () => {
    setLoading(true);
    try {
      const response = await clientApi.get('/api/calls', {
        params: {
          limit,
          offset,
        }
      });
      if (response.data) {
        setCalls(response.data.calls || []);
        setTotalCount(response.data.total_count || 0);
      }
    } catch (err) {
      console.warn('API error listing call logs', err);
    } finally {
      setLoading(false);
    }
  }, [limit, offset]);

  useEffect(() => {
    const timer = setTimeout(() => {
      loadCalls();
    }, 0);
    return () => clearTimeout(timer);
  }, [loadCalls]);

  // Load detailed call/transcript when row clicked
  const handleOpenTranscript = async (call) => {
    setSelectedCall(call);
    setIsDrawerOpen(true);
    setCallLoading(true);
    setIsPlaying(false);
    setPlaySeconds(84); // Reset playhead to default 1:24

    try {
      const response = await clientApi.get(`/api/calls/${call.session_call_id}`);
      if (response.data && response.data.session_call_id) {
        const call = response.data;
        if (typeof call.transcript === 'string') {
          try { call.transcript = JSON.parse(call.transcript); } catch { call.transcript = []; }
        }
        if (typeof call.extraction_json === 'string') {
          try { call.extraction_json = JSON.parse(call.extraction_json); } catch { call.extraction_json = null; }
        }
        setCallData(call);
      } else {
        throw new Error('Call details not returned');
      }
    } catch (err) {
      console.warn('API error fetching call transcript details', err);
      setCallData(null);
    } finally {
      setCallLoading(false);
    }
  };

  const handleCloseDrawer = () => {
    setIsDrawerOpen(false);
    setIsPlaying(false);
  };

  // Playback timer ticker simulation
  /* TODO: Playback timer ticker simulation (Phase 4 call recordings)
  useEffect(() => {
    if (!isPlaying || !callData) return;
    const maxDur = callData.duration_seconds || 252;
    const timer = setInterval(() => {
      setPlaySeconds(prev => {
        if (prev >= maxDur) {
          setIsPlaying(false);
          return 0;
        }
        return prev + 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [isPlaying, callData]);
  */

  // Formatter helpers
  const formatTime = (totalSecs) => {
    const mins = Math.floor(totalSecs / 60);
    const secs = totalSecs % 60;
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  };

  return (
    <>
      {/* Page Canvas (Split Pane Layout) */}
      <div className="flex flex-1 overflow-hidden relative w-full h-[calc(100vh-64px)]">
          
          {/* Table Container (Left Pane) - Narrows dynamically when drawer opens */}
          <div 
            id="mainTableArea" 
            className={`flex-1 flex flex-col p-margin-desktop overflow-hidden transition-all duration-300 ${isDrawerOpen ? 'lg:mr-[450px]' : 'mr-0'}`}
          >
            <div className="flex justify-between items-end mb-stack-md shrink-0">
              <div>
                <h3 className="font-headline-lg text-headline-lg text-on-surface dark:text-molten-text mb-1">Recent Transcripts</h3>
                <p className="font-body-sm text-body-sm text-on-surface-variant dark:text-molten-text-muted">Review automated extractions and conversation logs.</p>
              </div>
              <div className="flex gap-2">
                <button className="px-3 py-1.5 border border-outline-variant dark:border-molten-surface rounded-lg font-label-sm text-label-sm text-on-surface dark:text-molten-text hover:bg-surface-container dark:hover:bg-molten-surface transition-colors flex items-center gap-1 cursor-pointer">
                  <span className="material-symbols-outlined text-[16px]">filter_list</span> Filter
                </button>
              </div>
            </div>

            {/* Table */}
            <div className="bg-arctic-surface dark:bg-molten-bg border border-outline-variant/50 dark:border-molten-surface rounded-lg shadow-[0_4px_20px_rgba(22,71,232,0.05)] dark:shadow-none flex-1 overflow-hidden flex flex-col transition-colors duration-300">
              <div className="overflow-y-auto custom-scroll flex-1">
                <table className="w-full text-left border-collapse">
                  <thead className="bg-surface-container-low dark:bg-molten-surface/50 sticky top-0 z-10">
                    <tr>
                      <th className="py-3 px-4 font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted border-b border-outline-variant/30 dark:border-molten-surface uppercase tracking-wider">Lead Name</th>
                      <th className="py-3 px-4 font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted border-b border-outline-variant/30 dark:border-molten-surface uppercase tracking-wider">Phone</th>
                      <th className="py-3 px-4 font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted border-b border-outline-variant/30 dark:border-molten-surface uppercase tracking-wider">Duration</th>
                      <th className="py-3 px-4 font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted border-b border-outline-variant/30 dark:border-molten-surface uppercase tracking-wider">Status</th>
                      <th className="py-3 px-4 font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted border-b border-outline-variant/30 dark:border-molten-surface uppercase tracking-wider text-right">Time</th>
                    </tr>
                  </thead>
                  <tbody className="">
                    {loading && <LoaderOverlay isVisible={loading} message="Loading Transcripts..." />}
                    {!loading && calls.map((call) => {
                        const statusColors = 
                          call.status === 'completed'
                            ? 'bg-secondary/10 text-secondary dark:bg-molten-success/15 dark:text-molten-success'
                            : call.status === 'follow_up'
                            ? 'bg-arctic-warning/10 text-arctic-warning dark:bg-molten-warning/15 dark:text-molten-warning'
                            : call.status === 'failed'
                            ? 'bg-error/10 text-error dark:bg-molten-error/15 dark:text-molten-error'
                            : 'bg-outline-variant/30 text-on-surface-variant dark:bg-outline/20 dark:text-molten-text-muted';

                        const statusLabel = 
                          call.status === 'completed' ? 'Completed' :
                          call.status === 'follow_up' ? 'Follow-up Required' :
                          call.status === 'failed' ? 'Failed Connection' : 'Voicemail';

                        return (
                          <tr 
                            key={call.session_call_id} 
                            onClick={() => handleOpenTranscript(call)}
                            className="arctic-table-row hover:bg-surface-container-lowest dark:hover:bg-molten-surface/60 transition-colors cursor-pointer"
                          >
                            <td className="py-4 px-4 font-medium">{call.name || '—'}</td>
                            <td className="py-4 px-4 text-on-surface-variant dark:text-molten-text-muted">{call.phone}</td>
                            <td className="py-4 px-4">{formatTime(call.duration_seconds)}</td>
                            <td className="py-4 px-4">
                              <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full font-label-sm text-[11px] font-semibold ${statusColors}`}>
                                {statusLabel}
                              </span>
                            </td>
                            <td className="py-4 px-4 text-right text-on-surface-variant dark:text-molten-text-muted">
                              {call.time_label || formatDateTime(call.created_at)}
                            </td>
                          </tr>
                        );
                      })
                    }
                  </tbody>
                </table>
              </div>

              {/* Table Footer */}
              <div className="border-t border-outline-variant/30 dark:border-molten-surface p-3 flex justify-between items-center bg-surface-container-lowest dark:bg-molten-bg shrink-0">
                <span className="font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted">
                  Showing {offset + 1}-{Math.min(offset + limit, totalCount)} of {totalCount}
                </span>
                <div className="flex gap-1">
                  <button 
                    disabled={offset === 0}
                    onClick={() => setOffset(prev => Math.max(0, prev - limit))}
                    className="p-1 rounded hover:bg-surface-container dark:hover:bg-molten-surface text-on-surface-variant dark:text-molten-text-muted disabled:opacity-50 cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-[20px]">chevron_left</span>
                  </button>
                  <button 
                    disabled={offset + limit >= totalCount}
                    onClick={() => setOffset(prev => prev + limit)}
                    className="p-1 rounded hover:bg-surface-container dark:hover:bg-molten-surface text-on-surface-variant dark:text-molten-text-muted disabled:opacity-50 cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-[20px]">chevron_right</span>
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Transcript Drawer (Right Pane) - absolute overlay, slides in/out */}
          <div 
            id="transcriptDrawer" 
            className={`w-full sm:w-[450px] border-l border-outline-variant dark:border-molten-surface bg-surface-bright dark:bg-molten-bg flex flex-col absolute right-0 top-0 bottom-0 transition-transform duration-300 z-30 shadow-[-10px_0_30px_rgba(0,0,0,0.05)] dark:shadow-none ${
              isDrawerOpen ? 'drawer-slide-in translate-x-0' : 'drawer-slide-out translate-x-full'
            }`}
          >
            {selectedCall && (
              <>
                {/* Drawer Header */}
                <div className="p-4 border-b border-outline-variant/50 dark:border-molten-surface flex justify-between items-center shrink-0">
                  <div>
                    <h4 className="font-headline-sm text-headline-sm text-on-surface dark:text-molten-text" id="drawerName">
                      {selectedCall.name}
                    </h4>
                    <p className="font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted tabular-nums">
                      {selectedCall.time_label || 'Today'}
                      {/* TODO: duration tracker
                      • {formatTime(selectedCall.duration_seconds)}
                      */}
                    </p>
                  </div>
                  <button 
                    onClick={handleCloseDrawer} 
                    className="p-2 rounded-full hover:bg-surface-container dark:hover:bg-molten-surface text-on-surface-variant dark:text-molten-text-muted transition-colors cursor-pointer"
                  >
                    <span className="material-symbols-outlined">close</span>
                  </button>
                </div>

                {/* Drawer Scrollable Content */}
                <div className="flex-1 overflow-y-auto custom-scroll flex flex-col relative bg-arctic-bg dark:bg-molten-bg/40">
                  {callLoading ? (
                    <div className="flex-1 flex flex-col items-center justify-center p-8 text-primary">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
                      <p className="mt-2 text-sm text-arctic-text-muted">Loading transcript...</p>
                    </div>
                  ) : callData ? (
                    <>
                      {/* Extraction Sidebar */}
                      {callData.extraction_json && Object.keys(callData.extraction_json).length > 0 && (
                        <div className="bg-surface-container-low dark:bg-molten-surface/40 p-4 border-b border-outline-variant/30 dark:border-molten-surface shrink-0">
                          <div className="flex items-center gap-2 mb-3">
                            <span className="material-symbols-outlined text-[16px] text-primary dark:text-molten-primary">data_object</span>
                            <h5 className="font-label-sm text-label-sm text-on-surface dark:text-molten-text font-bold uppercase tracking-wider">Live Extraction</h5>
                          </div>
                          <div className="font-mono text-[13px] bg-arctic-surface dark:bg-molten-bg border border-outline-variant/30 dark:border-molten-surface p-3 rounded-md shadow-sm dark:shadow-none tabular-nums text-on-surface-variant dark:text-molten-text-muted space-y-1">
                            {"{"}
                            {Object.entries(callData.extraction_json).map(([key, val], idx, arr) => (
                              <div key={key} className="pl-4 flex justify-between">
                                <span>
                                  <span className="text-primary dark:text-molten-primary">"{key}"</span>:{" "}
                                  <span className={typeof val === 'string' ? 'text-secondary dark:text-molten-success' : 'text-on-surface dark:text-molten-text'}>
                                    {typeof val === 'string' ? `"${val}"` : String(val)}
                                  </span>
                                  {idx < arr.length - 1 ? ',' : ''}
                                </span>
                              </div>
                            ))}
                            {"}"}
                          </div>
                        </div>
                      )}

                      {/* Chat Bubbles */}
                      <div className="p-4 space-y-6 flex-1" id="chatContainer">
                        {Array.isArray(callData.transcript) && callData.transcript.map((msg, idx) => {
                          const isAi = msg.role === 'assistant' || msg.role === 'bot';
                          const delayClass = `delay-${idx > 3 ? 3 : idx}`;
                          return isAi ? (
                            <div key={idx} className={`flex flex-col mb-4 bubble-enter ${delayClass}`}>
                              <div className="flex items-center gap-1.5 mb-1 ml-1">
                                <span className="material-symbols-outlined text-[14px] text-primary dark:text-molten-primary animate-pulse">graphic_eq</span>
                                <span className="font-label-sm text-[11px] text-on-surface-variant dark:text-molten-text-muted uppercase tracking-wider">AI Agent</span>
                              </div>
                              <div className="bg-surface dark:bg-molten-surface border-l-2 border-primary-container dark:border-molten-primary p-3 rounded-lg rounded-tl-none self-start max-w-[85%] text-on-surface dark:text-molten-text font-body-sm shadow-sm dark:shadow-none">
                                {msg.content}
                              </div>
                            </div>
                          ) : (
                            <div key={idx} className={`flex flex-col mb-4 bubble-enter ${delayClass} items-end`}>
                              <div className="flex items-center gap-1.5 mb-1 mr-1">
                                <span className="font-label-sm text-[11px] text-on-surface-variant dark:text-molten-text-muted uppercase tracking-wider">Customer</span>
                              </div>
                              <div className="bg-primary text-on-primary dark:bg-inverse-surface dark:text-molten-text p-3 rounded-lg rounded-tr-none self-end max-w-[85%] font-body-sm shadow-[inset_0_1px_rgba(255,255,255,0.2)] dark:shadow-[inset_0_1px_rgba(255,255,255,0.05)] border border-transparent dark:border-outline-variant/10">
                                {msg.content}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </>
                  ) : (
                    <div className="flex-grow flex items-center justify-center text-arctic-text-muted">
                      Failed to fetch transcript details.
                    </div>
                  )}
                </div>

                {/* TODO: Call Recordings play/download (Phase 3) - disabled in client view */}
                {/* TODO: SSE live metrics / active call charts (Phase 3/4) */}
                {/* TODO: Call recordings playback support (Phase 4 CF R2 Integration)
                <div className="p-3 border-t border-outline-variant/50 dark:border-molten-surface bg-surface-container-lowest dark:bg-molten-bg shrink-0 flex items-center gap-3 transition-colors duration-300">
                  <button 
                    onClick={() => setIsPlaying(!isPlaying)}
                    className="p-2 rounded-full bg-primary text-on-primary dark:bg-molten-primary shadow-inner hover:brightness-95 active:scale-95 transition-all cursor-pointer flex items-center justify-center"
                  >
                    <span className="material-symbols-outlined fill">
                      {isPlaying ? 'pause' : 'play_arrow'}
                    </span>
                  </button>
                  <div className="flex-grow h-1.5 bg-surface-container-high dark:bg-molten-surface rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-primary dark:bg-molten-primary rounded-full transition-all duration-300"
                      style={{ width: `${(playSeconds / (selectedCall.duration_seconds || 252)) * 100}%` }}
                    ></div>
                  </div>
                  <span className="font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted tabular-nums">
                    {formatTime(playSeconds)} / {formatTime(selectedCall.duration_seconds)}
                  </span>
                </div>
                */}
                <div className="text-center w-full py-4 text-xs text-arctic-text-muted dark:text-molten-text-muted shrink-0 border-t border-outline-variant/50 dark:border-molten-surface bg-surface-container-lowest dark:bg-molten-bg">
                  Audio recordings will be available in Phase 4.
                </div>
              </>
            )}
          </div>

      </div>
    </>
  );
};

// Helper for formatting real dates if needed
const formatDateTime = (isoString) => {
  if (!isoString) return '—';
  const date = new Date(isoString);
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: true
  });
};

export default CallLogs;
