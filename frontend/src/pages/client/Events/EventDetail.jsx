import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import clientApi from "../../../api/client";
import EventLeadsTable from "./EventLeadsTable";
import "./EventDetails.css";

const formatDate = (dateTime) => {
  if (!dateTime) {
    return "—";
  }

  const date = new Date(dateTime);

  if (Number.isNaN(date.getTime())) {
    return "—";
  }

  return date.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
};

const getErrorMessage = (err, fallback) => {
  const detail = err.response?.data?.detail;

  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") {
          return item;
        }

        return item?.msg || JSON.stringify(item);
      })
      .join(", ");
  }

  if (detail && typeof detail === "object") {
    return detail.msg || JSON.stringify(detail);
  }

  return err.message || fallback;
};

const EventDetails = () => {
  const { eventId } = useParams();
  const navigate = useNavigate();

  const [event, setEvent] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [leads, setLeads] = useState([]);
  const [leadsLoading, setLeadsLoading] = useState(true);
  const [leadsError, setLeadsError] = useState(null);
  const [totalLeadsCount, setTotalLeadsCount] = useState(0);
  const [leadCounts, setLeadCounts] = useState({
    total_leads: 0,
    pending_leads: 0,
    calling_leads: 0,
    callback_leads: 0,
    completed_leads: 0,
    failed_leads: 0,
  });
  const loadEvent = async () => {
    try {
      setLoading(true);
      setError(null);

      const res = await clientApi.get(`/api/events/${eventId}`);

      setEvent(res.data?.event || null);
    } catch (err) {
      console.error("Failed to load event:", err);

      setError(getErrorMessage(err, "Failed to load event."));
    } finally {
      setLoading(false);
    }
  };

  const loadLeads = async () => {
    try {
      setLeadsLoading(true);
      setLeadsError(null);

      const res = await clientApi.get(`/api/events/${eventId}/leads`, {
        params: {
          limit: 500,
          offset: 0,
        },
      });

      setLeads(res.data?.leads || []);
      setTotalLeadsCount(res.data?.total_count || 0);
    } catch (err) {
      console.error("Failed to load event leads:", err);

      setLeads([]);
      setTotalLeadsCount(0);

      setLeadsError(getErrorMessage(err, "Failed to load leads."));
    } finally {
      setLeadsLoading(false);
    }
  };
  const loadLeadCounts = async () => {
    try {
      const res = await clientApi.get(`/api/events/${eventId}/lead-counts`);

      const counts = res.data?.counts || {};

      setLeadCounts({
        total_leads: counts.total_leads ?? 0,
        pending_leads: counts.pending_leads ?? 0,
        calling_leads: counts.calling_leads ?? 0,
        callback_leads: counts.callback_leads ?? 0,
        completed_leads: counts.completed_leads ?? 0,
        failed_leads: counts.failed_leads ?? 0,
      });
    } catch (err) {
      console.error("FAILED TO LOAD LEAD COUNTS:", err);
    }
  };
  useEffect(() => {
    if (!eventId) {
      return;
    }

    loadEvent();
    loadLeads();
    loadLeadCounts();
  }, [eventId]);

  if (loading) {
    return (
      <div className="cl-page-container app-page event-detail">
        <div className="event-detail__loading">
          <span className="material-symbols-outlined">progress_activity</span>
          <span>Loading event...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="cl-page-container app-page event-detail">
        <button
          type="button"
          className="event-detail__back"
          onClick={() => navigate("/app/events")}
        >
          <span className="material-symbols-outlined">arrow_back</span>
          Events
        </button>

        <div className="event-detail__error event-detail__error--page">
          <span className="material-symbols-outlined">error</span>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  if (!event) {
    return (
      <div className="cl-page-container app-page event-detail">
        <button
          type="button"
          className="event-detail__back"
          onClick={() => navigate("/app/events")}
        >
          <span className="material-symbols-outlined">arrow_back</span>
          Events
        </button>

        <div className="event-detail__empty">
          <span className="material-symbols-outlined">event_busy</span>
          <h2>Event not found</h2>
          <p>The event you're looking for could not be found.</p>
        </div>
      </div>
    );
  }

  const eventStatus = (event.status || "unknown")
    .toLowerCase()
    .replace(/\s+/g, "-");

  return (
    <div className="cl-page-container app-page event-detail">
      {/* =====================================================
    Header
    ===================================================== */}
      <div className="event-detail__header">
        <button
          type="button"
          className="event-detail__back"
          onClick={() => navigate("/app/events")}
        >
          <span className="material-symbols-outlined">arrow_back</span>
          Events
        </button>

        <div className="event-detail__header-info">
          <div className="event-detail__title-row">
            <div className="event-detail__title-wrapper">
              <span className="event-detail__eyebrow">EVENT</span>

              <h1>{event.name || "Untitled Event"}</h1>
            </div>

            <span
              className={`event-detail__status event-detail__status--${eventStatus}`}
            >
              <span className="event-detail__status-dot" />
              {event.status || "—"}
            </span>
          </div>

          {event.description && (
            <p className="event-detail__description">{event.description}</p>
          )}

          {/* Event information + Lead Sources */}
          <div className="event-detail__meta-row">
            {/* Left: Event information */}
            <div className="event-detail__meta">
              <span>
                <span className="material-symbols-outlined">fingerprint</span>

                <span className="event-detail__meta-label">Event ID</span>

                <span className="event-detail__id">{event.id}</span>
              </span>

              <span>
                <span className="material-symbols-outlined">
                  calendar_today
                </span>

                <span className="event-detail__meta-label">Created</span>

                <strong>{formatDate(event.created_at)}</strong>
              </span>

              <span>
                <span className="material-symbols-outlined">settings</span>

                <span className="event-detail__meta-label">Lead Handling</span>

                <strong>{event.lead_handling || "—"}</strong>
              </span>
            </div>

            {/* Right: Lead Sources */}
            <div className="event-detail__sources">
              <div className="event-detail__sources-heading">
                <span className="material-symbols-outlined">source</span>

                <span>Lead Sources</span>
              </div>

              <div className="event-detail__source-list">
                {event.source_types?.length ? (
                  event.source_types.map((source) => (
                    <span key={source} className="event-detail__source-badge">
                      <span className="material-symbols-outlined">dataset</span>

                      {source}
                    </span>
                  ))
                ) : (
                  <span className="event-detail__source-empty">No sources</span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* =====================================================
          Statistics
          ===================================================== */}
      <div className="event-detail__stats">
        <div className="event-detail__stat event-detail__stat--primary">
          <div className="event-detail__stat-icon">
            <span className="material-symbols-outlined">groups</span>
          </div>

          <div className="event-detail__stat-content">
            <span>Total Leads</span>
            <strong>{leadCounts.total_leads}</strong>
          </div>
        </div>

        <div className="event-detail__stat">
          <div className="event-detail__stat-icon">
            <span className="material-symbols-outlined">schedule</span>
          </div>

          <div className="event-detail__stat-content">
            <span>Pending</span>
            <strong>{leadCounts.pending_leads}</strong>
          </div>
        </div>

        <div className="event-detail__stat">
          <div className="event-detail__stat-icon">
            <span className="material-symbols-outlined">phone_in_talk</span>
          </div>

          <div className="event-detail__stat-content">
            <span>Calling</span>
            <strong>{leadCounts.calling_leads}</strong>
          </div>
        </div>

        <div className="event-detail__stat">
          <div className="event-detail__stat-icon">
            <span className="material-symbols-outlined">phone_callback</span>
          </div>

          <div className="event-detail__stat-content">
            <span>Callbacks</span>
            <strong>{leadCounts.callback_leads}</strong>
          </div>
        </div>

        <div className="event-detail__stat">
          <div className="event-detail__stat-icon">
            <span className="material-symbols-outlined">check_circle</span>
          </div>

          <div className="event-detail__stat-content">
            <span>Completed</span>
            <strong>{leadCounts.completed_leads}</strong>
          </div>
        </div>

        <div className="event-detail__stat">
          <div className="event-detail__stat-icon">
            <span className="material-symbols-outlined">error</span>
          </div>

          <div className="event-detail__stat-content">
            <span>Failed</span>
            <strong>{leadCounts.failed_leads}</strong>
          </div>
        </div>
      </div>

      {/* =====================================================
          Leads Error
          ===================================================== */}
      {leadsError && (
        <div className="event-detail__error">
          <span className="material-symbols-outlined">error</span>

          <span>{leadsError}</span>
        </div>
      )}

      {/* =====================================================
          Leads Table
          ===================================================== */}
      <EventLeadsTable
        leads={leads}
        leadsLoading={leadsLoading}
        totalLeadsCount={totalLeadsCount}
        eventId={eventId}
        onLeadsChanged={async () => {
          await Promise.all([loadEvent(), loadLeads(), loadLeadCounts()]);
        }}
      />
    </div>
  );
};

export default EventDetails;
