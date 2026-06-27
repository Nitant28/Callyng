import { useState, useEffect, useCallback } from 'react';
import { useTheme } from '../../hooks/useTheme';
import clientApi from '../../api/client';
import LoaderOverlay from '../../components/shared/LoaderOverlay';

const CallLogs = () => {
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
  const [recordingUrl, setRecordingUrl] = useState(null);
  const [recordingLoading, setRecordingLoading] = useState(false);
  const [recordingError, setRecordingError] = useState(null);
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
    const sessionCallId = call.session_call_id;
    setSelectedCall(call);
    setIsDrawerOpen(true);
    setCallLoading(true);
    setIsPlaying(false);
    setPlaySeconds(84);
    setRecordingUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    setRecordingError(null);

    let callDetails = null;
    try {
      const response = await clientApi.get(`/api/calls/${sessionCallId}`);
      if (response.data && response.data.session_call_id) {
        callDetails = response.data;
        if (typeof callDetails.transcript === 'string') {
          try { callDetails.transcript = JSON.parse(callDetails.transcript); } catch { callDetails.transcript = []; }
        }
        if (typeof callDetails.extraction_json === 'string') {
          try { callDetails.extraction_json = JSON.parse(callDetails.extraction_json); } catch { callDetails.extraction_json = null; }
        }
        setCallData(callDetails);
      } else {
        throw new Error('Call details not returned');
      }
    } catch (err) {
      console.warn('API error fetching call transcript details', err);
      setCallData(null);
    } finally {
      setCallLoading(false);
    }

    const resolvedSessionCallId = callDetails?.session_call_id || sessionCallId;
    setRecordingLoading(true);
    try {
      const recResp = await clientApi.get(`/api/calls/${resolvedSessionCallId}/recording/play`, {
        responseType: 'blob'
      });
      const url = URL.createObjectURL(recResp.data);
      setRecordingUrl(url);
    } catch (err) {
      setRecordingError(err.response?.data?.detail || "No recording available");
    } finally {
      setRecordingLoading(false);
    }
  };

  const handleCloseDrawer = () => {
    setRecordingUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    setIsDrawerOpen(false);
  };



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
              <div className="overflow-y-auto custom-scroll flex-1 relative">
                {loading && <LoaderOverlay isVisible={loading} message="Loading Transcripts..." />}
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

                {/* Call Recording */}
                <div className="p-4 border-t border-outline-variant/50 dark:border-molten-surface bg-surface-container-lowest dark:bg-molten-bg shrink-0 transition-colors duration-300">
                  {recordingLoading ? (
                    <div className="flex justify-center items-center gap-2 text-sm text-arctic-text-muted dark:text-molten-text-muted py-2">
                      <span className="material-symbols-outlined animate-spin text-lg">progress_activity</span>
                      Loading audio...
                    </div>
                  ) : recordingUrl ? (
                    <audio controls src={recordingUrl} className="w-full h-10 outline-none" controlsList="nodownload" />
                  ) : (
                    <div className="text-center text-xs text-arctic-text-muted dark:text-molten-text-muted">
                      {recordingError || "Audio recordings will be available after call completes."}
                    </div>
                  )}
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
