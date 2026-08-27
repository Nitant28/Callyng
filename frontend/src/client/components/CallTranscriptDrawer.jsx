import { useState, useEffect, useRef, useCallback } from "react";
import clientApi from "../../api/client";

const CallTranscriptDrawer = ({ isOpen, sessionCallId, onClose, leadName, leadData }) => {
  const [activeTab, setActiveTab] = useState("analytics");
  const [callData, setCallData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [isPolling, setIsPolling] = useState(false);
  const [transcriptSearch, setTranscriptSearch] = useState("");
  const [recordingUrl, setRecordingUrl] = useState(null);
  const [recordingLoading, setRecordingLoading] = useState(false);
  const [recordingError, setRecordingError] = useState(null);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [isPlaying, setIsPlaying] = useState(false);
  const [audioProgress, setAudioProgress] = useState(0);
  const [audioDuration, setAudioDuration] = useState(0);
  const [speedMenuOpen, setSpeedMenuOpen] = useState(false);
  const audioRef = useRef(null);

  const fmt = (s) => {
    if (!s && s !== 0) return "—";
    const m = Math.floor(s / 60), sec = Math.round(s % 60);
    return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  };
  const fmtTime = (t) => {
    if (isNaN(t)) return "0:00";
    const m = Math.floor(t / 60), s = Math.floor(t % 60);
    return `${m}:${s < 10 ? "0" : ""}${s}`;
  };
  const initials = (name) =>
    name ? name.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase() : "LD";

  const OUTCOME_COLORS = {
    Interested: { bg: "#d1fae5", text: "#065f46", border: "#6ee7b7" },
    Not_Interested: { bg: "#fee2e2", text: "#991b1b", border: "#fca5a5" },
    Callback_Requested: { bg: "#fef3c7", text: "#92400e", border: "#fcd34d" },
    Busy: { bg: "#fef3c7", text: "#92400e", border: "#fcd34d" },
  };
  const outcomeStyle = (o) => OUTCOME_COLORS[o] || { bg: "#f1f5f9", text: "#475569", border: "#cbd5e1" };

  const fetchCallDetails = useCallback(async (showSpinner = true) => {
    if (!sessionCallId) return;
    if (showSpinner) setLoading(true);
    try {
      const res = await clientApi.get(`/api/calls/${sessionCallId}`);
      if (res.data?.session_call_id) {
        const call = res.data;
        if (typeof call.transcript === "string") {
          try { call.transcript = JSON.parse(call.transcript); } catch { call.transcript = []; }
        }
        if (typeof call.extraction_json === "string") {
          try { call.extraction_json = JSON.parse(call.extraction_json); } catch { call.extraction_json = null; }
        }
        setCallData(call);
        setIsPolling(call.in_progress === true);
      }
    } catch {
      setCallData(null);
      setIsPolling(false);
    } finally {
      if (showSpinner) setLoading(false);
    }
  }, [sessionCallId]);

  useEffect(() => {
    if (isOpen && sessionCallId) {
      setActiveTab("analytics");
      setTranscriptSearch("");
      fetchCallDetails(true);
    } else {
      setCallData(null);
      setIsPolling(false);
    }
  }, [isOpen, sessionCallId, fetchCallDetails]);

  useEffect(() => {
    if (!isPolling || !isOpen || !sessionCallId) return;
    const interval = setInterval(() => fetchCallDetails(false), 2000);
    return () => clearInterval(interval);
  }, [isPolling, isOpen, sessionCallId, fetchCallDetails]);

  const fetchRecording = useCallback(async (id, inProgress) => {
    if (!id) return;
    setRecordingLoading(true);
    setRecordingError(null);
    try {
      const res = await clientApi.get(`/api/calls/${id}/recording/play`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      setRecordingUrl(prev => { if (prev) URL.revokeObjectURL(prev); return url; });
    } catch (err) {
      setRecordingUrl(prev => { if (prev) URL.revokeObjectURL(prev); return null; });
      if (!inProgress) setRecordingError(err.response?.data?.detail || "No recording available");
    } finally {
      setRecordingLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isOpen || !callData?.session_call_id) return;
    fetchRecording(callData.session_call_id, callData.in_progress);
  }, [isOpen, callData?.session_call_id, callData?.in_progress, fetchRecording]);

  useEffect(() => {
    if (isOpen) return;
    setRecordingUrl(prev => { if (prev) URL.revokeObjectURL(prev); return null; });
    setRecordingError(null);
    setRecordingLoading(false);
    setIsPlaying(false);
    setAudioProgress(0);
  }, [isOpen]);

  const togglePlay = () => {
    if (!audioRef.current) return;
    if (isPlaying) { audioRef.current.pause(); setIsPlaying(false); }
    else { audioRef.current.play().then(() => setIsPlaying(true)).catch(() => {}); }
  };
  const skipTime = (amt) => {
    if (!audioRef.current) return;
    audioRef.current.currentTime = Math.max(0, Math.min(audioDuration, audioRef.current.currentTime + amt));
  };
  const changeSpeed = (sp) => {
    if (audioRef.current) audioRef.current.playbackRate = sp;
    setPlaybackSpeed(sp);
    setSpeedMenuOpen(false);
  };

  const computeAnalytics = () => {
    if (!callData?.transcript || !Array.isArray(callData.transcript)) {
      return { aiRatio: 0, custRatio: 0, turns: 0, aiTurns: 0, custTurns: 0, avgResponse: 0 };
    }
    let aiWords = 0, custWords = 0, aiTurns = 0, custTurns = 0;
    callData.transcript.forEach(t => {
      const w = (t.content || "").split(/\s+/).filter(Boolean).length;
      if (t.role === "assistant" || t.role === "bot") { aiWords += w; aiTurns++; }
      else { custWords += w; custTurns++; }
    });
    const totalWords = aiWords + custWords || 1;
    const totalTurns = aiTurns + custTurns;
    const avgResponse = totalTurns > 0 ? Math.round((callData.duration_seconds || 0) / totalTurns * 10) / 10 : 0;
    return {
      aiRatio: Math.round((aiWords / totalWords) * 100),
      custRatio: Math.round((custWords / totalWords) * 100),
      turns: totalTurns, aiTurns, custTurns, avgResponse,
    };
  };

  const stats = computeAnalytics();
  const outcome = callData?.outcome || leadData?.outcome || "";
  const phone = callData?.phone || leadData?.phone || "";
  const outStyle = outcomeStyle(outcome);
  const extractionEntries = callData?.extraction_json ? Object.entries(callData.extraction_json) : [];
  const filteredTranscript = (callData?.transcript || []).filter(t =>
    !transcriptSearch || (t.content || "").toLowerCase().includes(transcriptSearch.toLowerCase())
  );

  if (!isOpen) return null;

  const circleBtn = (sz, bg, extra) => ({
    width: sz, height: sz, borderRadius: "50%", border: "none",
    background: bg, display: "flex", alignItems: "center",
    justifyContent: "center", cursor: "pointer", ...extra,
  });

  return (
    <>
      <div style={{
        position: "fixed", right: 0, top: 0, bottom: 0, zIndex: 50,
        width: "420px", display: "flex", flexDirection: "column",
        background: "#fff", borderLeft: "1px solid #e8ecf2",
        boxShadow: "-8px 0 32px rgba(0,0,0,0.10)",
        fontFamily: "'Inter', -apple-system, sans-serif",
      }}>

        {/* HEADER */}
        <div style={{ padding: "16px 20px 0", borderBottom: "1px solid #f0f2f7", flexShrink: 0 }}>
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10, paddingBottom: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
              {/* Avatar */}
              <div style={{
                width: 42, height: 42, borderRadius: 12, flexShrink: 0,
                background: "linear-gradient(135deg,#2563eb 0%,#7c3aed 100%)",
                display: "flex", alignItems: "center", justifyContent: "center",
                color: "#fff", fontWeight: 700, fontSize: 14, letterSpacing: 1,
              }}>
                {initials(leadName)}
              </div>
              <div style={{ minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 7, flexWrap: "wrap" }}>
                  <span style={{ fontWeight: 700, fontSize: 15, color: "#0f172a" }}>
                    {leadName || "Call Record"}
                  </span>
                  {outcome && (
                    <span style={{
                      fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em",
                      padding: "2px 7px", borderRadius: 4,
                      background: outStyle.bg, color: outStyle.text, border: `1px solid ${outStyle.border}`,
                    }}>
                      {outcome.replace(/_/g, " ")}
                    </span>
                  )}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 5, marginTop: 3, color: "#64748b", fontSize: 12 }}>
                  {phone && (
                    <>
                      <span className="material-symbols-outlined" style={{ fontSize: 13, color: "#94a3b8" }}>call</span>
                      <span style={{ fontFamily: "monospace" }}>{phone}</span>
                      <span style={{ color: "#dde1ea" }}>·</span>
                    </>
                  )}
                  <span>
                    {callData?.created_at
                      ? new Date(callData.created_at).toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" })
                      : "—"}
                  </span>
                </div>
              </div>
            </div>
            <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
              <button title="Expand" style={{ width: 30, height: 30, borderRadius: 7, border: "1px solid #e8ecf2", background: "#f8fafc", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", color: "#64748b" }}>
                <span className="material-symbols-outlined" style={{ fontSize: 15 }}>open_in_new</span>
              </button>
              <button onClick={onClose} title="Close" style={{ width: 30, height: 30, borderRadius: 7, border: "1px solid #e8ecf2", background: "#f8fafc", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", color: "#64748b" }}>
                <span className="material-symbols-outlined" style={{ fontSize: 17 }}>close</span>
              </button>
            </div>
          </div>

          {/* Tabs */}
          <div style={{ display: "flex" }}>
            {[
              { id: "analytics", label: "Analytics" },
              { id: "extracted", label: "Extracted Info" },
              { id: "transcript", label: "Transcript" },
            ].map(tab => (
              <button key={tab.id} onClick={() => setActiveTab(tab.id)} style={{
                padding: "9px 14px", fontSize: 13, fontWeight: 600,
                border: "none", background: "none", cursor: "pointer",
                color: activeTab === tab.id ? "#2563eb" : "#64748b",
                borderBottom: activeTab === tab.id ? "2px solid #2563eb" : "2px solid transparent",
                marginBottom: -1, transition: "all 0.15s ease",
              }}>
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {/* SCROLLABLE BODY */}
        <div style={{ flex: 1, overflowY: "auto", background: "#f8fafc" }}>
          {loading ? (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: 12, color: "#94a3b8" }}>
              <div style={{ width: 22, height: 22, borderRadius: "50%", border: "2.5px solid #2563eb", borderTopColor: "transparent", animation: "ctd-spin 0.8s linear infinite" }} />
              <span style={{ fontSize: 13 }}>Loading call data...</span>
            </div>
          ) : !callData ? (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#94a3b8", fontSize: 13 }}>
              No data available for this call.
            </div>
          ) : (
            <>
              {/* ANALYTICS TAB */}
              {activeTab === "analytics" && (
                <div style={{ padding: "18px 20px" }}>
                  <div style={{ background: "#fff", borderRadius: 12, padding: 16, border: "1px solid #e8ecf2", marginBottom: 12 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ fontSize: 13, fontWeight: 600, color: "#0f172a" }}>Talk Ratio</span>
                        <span className="material-symbols-outlined" style={{ fontSize: 15, color: "#94a3b8" }}>info</span>
                      </div>
                      <span style={{ fontSize: 12, color: "#64748b" }}>{stats.turns} total turns</span>
                    </div>
                    <div style={{ height: 8, borderRadius: 999, background: "#f1f5f9", overflow: "hidden", display: "flex", marginBottom: 10 }}>
                      <div style={{ width: `${stats.aiRatio}%`, background: "#2563eb", transition: "width 0.6s ease" }} />
                      <div style={{ flex: 1, background: "#22c55e" }} />
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                      <span style={{ color: "#2563eb", fontWeight: 600 }}>AI Agent {stats.aiRatio}%</span>
                      <span style={{ color: "#16a34a", fontWeight: 600 }}>Customer {stats.custRatio}%</span>
                    </div>
                  </div>

                  <div style={{ background: "#fff", borderRadius: 12, border: "1px solid #e8ecf2", overflow: "hidden" }}>
                    {[
                      { icon: "timer", label: "Duration", value: fmt(callData.duration_seconds) },
                      { icon: "swap_horiz", label: "Turns", value: stats.turns },
                      { icon: "smart_toy", label: "AI Turns", value: `${stats.aiTurns} (${stats.aiRatio}%)` },
                      { icon: "person", label: "Customer Turns", value: `${stats.custTurns} (${stats.custRatio}%)` },
                      { icon: "avg_pace", label: "Avg Response", value: stats.avgResponse ? `${stats.avgResponse}s` : "—" },
                    ].map((item, i, arr) => (
                      <div key={item.label} style={{
                        display: "flex", alignItems: "center", gap: 12, padding: "11px 16px",
                        borderBottom: i < arr.length - 1 ? "1px solid #f0f2f7" : "none",
                      }}>
                        <div style={{ width: 32, height: 32, borderRadius: 8, background: "#eff6ff", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                          <span className="material-symbols-outlined" style={{ fontSize: 17, color: "#2563eb" }}>{item.icon}</span>
                        </div>
                        <div>
                          <div style={{ fontSize: 11, color: "#94a3b8", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.05em" }}>{item.label}</div>
                          <div style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", marginTop: 1 }}>{item.value}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* EXTRACTED INFO TAB */}
              {activeTab === "extracted" && (
                <div style={{ padding: "18px 20px" }}>
                  {extractionEntries.length > 0 ? (
                    <>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
                        <span className="material-symbols-outlined" style={{ fontSize: 16, color: "#2563eb" }}>data_object</span>
                        <span style={{ fontSize: 11, fontWeight: 700, color: "#475569", textTransform: "uppercase", letterSpacing: "0.07em" }}>Extracted Info</span>
                      </div>
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(155px, 1fr))", gap: 10 }}>
                        {extractionEntries.map(([key, val]) => (
                          <div key={key} style={{ background: "#fff", border: "1px solid #e8ecf2", borderRadius: 10, padding: "10px 14px" }}>
                            <div style={{ fontSize: 10, color: "#94a3b8", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
                              {key.replace(/_/g, " ")}
                            </div>
                            <div style={{ fontSize: 13, fontWeight: 600, color: key.toLowerCase() === "intent" ? "#2563eb" : "#0f172a" }}>
                              {String(val)}
                            </div>
                          </div>
                        ))}
                      </div>
                    </>
                  ) : (
                    <div style={{ textAlign: "center", color: "#94a3b8", fontSize: 13, padding: "48px 0" }}>
                      No extracted data available for this call.
                    </div>
                  )}
                </div>
              )}

              {/* TRANSCRIPT TAB */}
              {activeTab === "transcript" && (
                <div style={{ padding: "14px 20px 12px" }}>
                  <div style={{ position: "relative", marginBottom: 14 }}>
                    <span className="material-symbols-outlined" style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", fontSize: 16, color: "#94a3b8", pointerEvents: "none" }}>search</span>
                    <input
                      type="text"
                      placeholder="Search in transcript..."
                      value={transcriptSearch}
                      onChange={e => setTranscriptSearch(e.target.value)}
                      style={{ width: "100%", padding: "7px 12px 7px 34px", borderRadius: 8, border: "1px solid #e8ecf2", fontSize: 12, outline: "none", background: "#fff", boxSizing: "border-box", color: "#0f172a" }}
                    />
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                    {filteredTranscript.length > 0 ? (
                      filteredTranscript.map((turn, i) => {
                        const isAi = turn.role === "assistant" || turn.role === "bot";
                        return (
                          <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: isAi ? "flex-start" : "flex-end" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 4, ...(isAi ? {} : { flexDirection: "row-reverse" }) }}>
                              <div style={{ width: 20, height: 20, borderRadius: 5, background: isAi ? "#eff6ff" : "#f0fdf4", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                                <span className="material-symbols-outlined" style={{ fontSize: 12, color: isAi ? "#2563eb" : "#16a34a" }}>
                                  {isAi ? "smart_toy" : "person"}
                                </span>
                              </div>
                              <span style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                                {isAi ? "AI Agent" : "Customer"}
                              </span>
                              {turn.timestamp != null && (
                                <span style={{ fontSize: 10, color: "#cbd5e1", fontFamily: "monospace" }}>{fmtTime(turn.timestamp)}</span>
                              )}
                            </div>
                            <div style={{
                              maxWidth: "82%", padding: "8px 12px",
                              borderRadius: isAi ? "3px 12px 12px 12px" : "12px 3px 12px 12px",
                              fontSize: 13, lineHeight: 1.55,
                              background: isAi ? "#fff" : "#2563eb",
                              color: isAi ? "#0f172a" : "#fff",
                              border: isAi ? "1px solid #e8ecf2" : "none",
                              boxShadow: isAi ? "0 1px 3px rgba(0,0,0,0.04)" : "none",
                            }}>
                              {turn.content}
                            </div>
                          </div>
                        );
                      })
                    ) : (
                      <div style={{ textAlign: "center", color: "#94a3b8", fontSize: 13, padding: "32px 0" }}>
                        {transcriptSearch ? "No matching messages." : "No transcript available."}
                      </div>
                    )}
                    {callData?.in_progress && (
                      <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
                        <div style={{ width: 20, height: 20, borderRadius: 5, background: "#eff6ff", display: "flex", alignItems: "center", justifyContent: "center" }}>
                          <span className="material-symbols-outlined" style={{ fontSize: 12, color: "#2563eb" }}>smart_toy</span>
                        </div>
                        <div style={{ background: "#fff", border: "1px solid #e8ecf2", borderRadius: "3px 12px 12px 12px", padding: "9px 14px", display: "flex", gap: 4, alignItems: "center" }}>
                          {[0, 1, 2].map(d => (
                            <div key={d} className="typing-dot" style={{ width: 5, height: 5, borderRadius: "50%", background: "#94a3b8", animationDelay: `${d * -0.16}s` }} />
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* AUDIO PLAYER */}
        <div style={{ flexShrink: 0, background: "#0f172a", borderTop: "1px solid #1e293b" }}>
          <audio
            ref={audioRef}
            src={recordingUrl || undefined}
            onTimeUpdate={() => setAudioProgress(audioRef.current?.currentTime || 0)}
            onLoadedMetadata={() => setAudioDuration(audioRef.current?.duration || 0)}
            onEnded={() => setIsPlaying(false)}
            style={{ display: "none" }}
          />
          {recordingLoading ? (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, padding: "14px 20px", color: "#475569", fontSize: 12 }}>
              <div style={{ width: 14, height: 14, borderRadius: "50%", border: "2px solid #3b82f6", borderTopColor: "transparent", animation: "ctd-spin 0.8s linear infinite" }} />
              Loading audio...
            </div>
          ) : recordingUrl ? (
            <div style={{ padding: "12px 20px", display: "flex", flexDirection: "column", gap: 8 }}>
              <div
                style={{ height: 34, display: "flex", alignItems: "center", gap: 1.5, cursor: "pointer" }}
                onClick={(e) => {
                  if (!audioRef.current || !audioDuration) return;
                  const rect = e.currentTarget.getBoundingClientRect();
                  const t = ((e.clientX - rect.left) / rect.width) * audioDuration;
                  audioRef.current.currentTime = t;
                  setAudioProgress(t);
                }}
              >
                {Array.from({ length: 72 }).map((_, i) => {
                  const active = audioDuration > 0 && (audioProgress / audioDuration) > (i / 72);
                  const h = Math.abs(Math.sin(i * 0.47) * 11) + Math.abs(Math.cos(i * 0.31) * 5) + 4;
                  return <div key={i} style={{ width: 2.5, height: `${h}px`, borderRadius: 999, flexShrink: 0, background: active ? "#60a5fa" : "rgba(148,163,184,0.22)" }} />;
                })}
              </div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontSize: 11, color: "#475569", fontFamily: "monospace", minWidth: 84 }}>
                  {fmtTime(audioProgress)} / {fmtTime(audioDuration)}
                </span>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <button onClick={() => skipTime(-15)} style={circleBtn(30, "#1e293b", { color: "#94a3b8" })}>
                    <span className="material-symbols-outlined" style={{ fontSize: 16 }}>replay_15</span>
                  </button>
                  <button onClick={togglePlay} style={circleBtn(40, "#2563eb", { color: "#fff", boxShadow: "0 0 14px rgba(37,99,235,0.4)" })}>
                    <span className="material-symbols-outlined" style={{ fontSize: 22 }}>{isPlaying ? "pause" : "play_arrow"}</span>
                  </button>
                  <button onClick={() => skipTime(15)} style={circleBtn(30, "#1e293b", { color: "#94a3b8" })}>
                    <span className="material-symbols-outlined" style={{ fontSize: 16 }}>forward_15</span>
                  </button>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 7, minWidth: 84, justifyContent: "flex-end" }}>
                  <div style={{ position: "relative" }}>
                    <button onClick={() => setSpeedMenuOpen(v => !v)} style={{ padding: "3px 7px", borderRadius: 6, background: "#1e293b", border: "1px solid #334155", color: "#94a3b8", fontSize: 11, fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", gap: 2 }}>
                      {playbackSpeed}x
                      <span className="material-symbols-outlined" style={{ fontSize: 12 }}>expand_more</span>
                    </button>
                    {speedMenuOpen && (
                      <div style={{ position: "absolute", bottom: "110%", right: 0, background: "#1e293b", border: "1px solid #334155", borderRadius: 8, padding: 4, display: "flex", flexDirection: "column", gap: 1, zIndex: 20 }}>
                        {[0.75, 1, 1.25, 1.5, 2].map(sp => (
                          <button key={sp} onClick={() => changeSpeed(sp)} style={{ padding: "5px 16px", background: playbackSpeed === sp ? "#2563eb" : "transparent", border: "none", borderRadius: 6, color: playbackSpeed === sp ? "#fff" : "#94a3b8", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
                            {sp}x
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  <a href={recordingUrl} download={`call_${phone || "recording"}.mp3`} style={{ width: 28, height: 28, borderRadius: 6, background: "#1e293b", display: "flex", alignItems: "center", justifyContent: "center", color: "#64748b", textDecoration: "none" }}>
                    <span className="material-symbols-outlined" style={{ fontSize: 14 }}>download</span>
                  </a>
                </div>
              </div>
            </div>
          ) : (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "11px 20px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 7, color: "#475569", fontSize: 12 }}>
                <span className="material-symbols-outlined" style={{ fontSize: 16, color: "#64748b" }}>mic_off</span>
                <span>{recordingError || (callData?.in_progress ? "Recording available after call ends." : "No recording available.")}</span>
              </div>
              <button onClick={onClose} style={{ padding: "4px 12px", borderRadius: 6, background: "#1e293b", border: "none", color: "#64748b", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>Close</button>
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes ctd-spin { to { transform: rotate(360deg); } }
        .typing-dot { animation: ctd-pulse 1.4s ease-in-out infinite both; }
        @keyframes ctd-pulse { 0%,80%,100% { transform:scale(.7);opacity:.5; } 40% { transform:scale(1);opacity:1; } }
      `}</style>
    </>
  );
};

export default CallTranscriptDrawer;
