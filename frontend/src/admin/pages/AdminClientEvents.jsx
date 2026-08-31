import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import adminApi from "../../shared/api/admin";
import { useAdminData } from "../contexts/AdminDataContext";
import "./AdminClientEvents.css";
import AdminCreateEvent from "./AdminCreateEvent";

export default function AdminClientEvents() {
  const { clientId } = useParams();
  const navigate = useNavigate();
  const { clientsMap, botConfigsMap } = useAdminData();

  const [events, setEvents] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deletingEventId, setDeletingEventId] = useState(null);
  const [editingEventId, setEditingEventId] = useState(null);

  const client = clientsMap[clientId];

  useEffect(() => {
    if (!clientId) return;

    const fetchClientEvents = async () => {
      try {
        setLoading(true);
        setError("");

        const res = await adminApi.get(
          `/internal/events?client_id=${clientId}`,
        );

        setEvents(res.data?.events || []);
      } catch (err) {
        console.error("Failed to fetch client events:", err);
        setError("Failed to load events.");
      } finally {
        setLoading(false);
      }
    };

    fetchClientEvents();
  }, [clientId]);

  const filteredEvents = useMemo(() => {
    const query = search.trim().toLowerCase();

    if (!query) return events;

    return events.filter(
      (event) =>
        event.name?.toLowerCase().includes(query) ||
        event.description?.toLowerCase().includes(query),
    );
  }, [events, search]);

  const formatDate = (dateTime) => {
    if (!dateTime) return "—";

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

  const getStatusClass = (status) =>
    `admin-client-events__status admin-client-events__status--${
      status || "unknown"
    }`;

  const handleDeleteEvent = async (event) => {
    const confirmed = window.confirm(
      `Are you sure you want to delete "${event.name}"?`,
    );

    if (!confirmed) return;

    try {
      setDeletingEventId(event.id);

      await adminApi.delete(`/internal/events/${event.id}`);

      setEvents((prev) => prev.filter((item) => item.id !== event.id));
    } catch (err) {
      console.error("Failed to delete event:", err);
      setError("Failed to delete event.");
    } finally {
      setDeletingEventId(null);
    }
  };

  return (
    <div className="admin-page admin-client-events">
      {/* =====================================================
          Header
          ===================================================== */}
      <div className="admin-page__header admin-client-events__header">
        <div>
          <button
            type="button"
            className="admin-client-events__back"
            onClick={() => navigate("/admin/events")}
          >
            <span className="material-symbols-outlined">arrow_back</span>
            Events
          </button>

          <div className="admin-client-events__eyebrow">
            <span className="material-symbols-outlined">business</span>
            CLIENT EVENTS
          </div>

          <h1 className="admin-page__title">
            {client?.name || "Client Events"}
          </h1>

          <p className="admin-page__subtitle">
            Manage AI calling events and lead workflows for this client.
          </p>
        </div>

        <button
          type="button"
          className="admin-button admin-button--primary"
          onClick={() => navigate(`/admin/events/create?client_id=${clientId}`)}
        >
          <span className="material-symbols-outlined">add</span>
          Create Event
        </button>
      </div>

      {/* =====================================================
          Client Summary
          ===================================================== */}
      <div className="admin-card admin-client-events__summary">
        <div className="admin-client-events__summary-icon">
          <span className="material-symbols-outlined">business</span>
        </div>

        <div className="admin-client-events__summary-info">
          <span>CLIENT</span>
          <strong>{client?.name || "Unknown Client"}</strong>
        </div>

        <div className="admin-client-events__summary-divider" />

        <div className="admin-client-events__summary-stat">
          <span>EVENTS</span>
          <strong>{events.length}</strong>
        </div>

        <div className="admin-client-events__summary-stat">
          <span>ACTIVE</span>
          <strong>
            {events.filter((event) => event.status === "active").length}
          </strong>
        </div>

        <div className="admin-client-events__summary-stat">
          <span>LEADS</span>
          <strong>
            {events.reduce(
              (sum, event) => sum + Number(event.total_leads || 0),
              0,
            )}
          </strong>
        </div>
      </div>

      {/* =====================================================
          Search
          ===================================================== */}
      <div className="admin-card admin-client-events__toolbar">
        <div className="admin-client-events__search">
          <span className="material-symbols-outlined">search</span>

          <input
            type="text"
            placeholder="Search events..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />

          {search && (
            <button
              type="button"
              onClick={() => setSearch("")}
              aria-label="Clear search"
            >
              <span className="material-symbols-outlined">close</span>
            </button>
          )}
        </div>

        <span className="admin-client-events__result-count">
          {filteredEvents.length}{" "}
          {filteredEvents.length === 1 ? "event" : "events"}
        </span>
      </div>

      {/* =====================================================
          Events List
          ===================================================== */}
      {loading ? (
        <div className="admin-card admin-client-events__empty">
          <div className="admin-client-events__empty-icon">
            <span className="material-symbols-outlined">sync</span>
          </div>

          <h3>Loading events...</h3>
          <p>Fetching this client's event configurations.</p>
        </div>
      ) : error ? (
        <div className="admin-card admin-client-events__empty">
          <div className="admin-client-events__empty-icon">
            <span className="material-symbols-outlined">error</span>
          </div>

          <h3>Unable to load events</h3>
          <p>{error}</p>
        </div>
      ) : filteredEvents.length === 0 ? (
        <div className="admin-card admin-client-events__empty">
          <div className="admin-client-events__empty-icon">
            <span className="material-symbols-outlined">
              {search ? "search_off" : "event"}
            </span>
          </div>

          <h3>{search ? "No events found" : "No events yet"}</h3>

          <p>
            {search
              ? "Try searching with a different event name."
              : "This client does not have any configured events yet."}
          </p>

          {!search && (
            <button
              type="button"
              className="admin-button admin-button--primary"
              onClick={() =>
                navigate(`/admin/events/create?client_id=${clientId}`)
              }
            >
              <span className="material-symbols-outlined">add</span>
              Create Event
            </button>
          )}
        </div>
      ) : (
        <div className="admin-client-events__list">
          {filteredEvents.map((event) => (
            <div
              key={event.id}
              className="admin-card admin-client-events__event"
            >
              {/* Left side */}
              <div className="admin-client-events__event-main">
                <div className="admin-client-events__event-icon">
                  <span className="material-symbols-outlined">event</span>
                </div>

                <div className="admin-client-events__event-info">
                  <div className="admin-client-events__event-title-row">
                    <h2>{event.name || "Untitled Event"}</h2>

                    <span className={getStatusClass(event.status)}>
                      {event.status || "Unknown"}
                    </span>
                  </div>

                  <p>
                    {event.description ||
                      "No description configured for this event."}
                  </p>

                  <div className="admin-client-events__event-meta">
                    <span>
                      <span className="material-symbols-outlined">source</span>
                      {event.source_types?.length
                        ? event.source_types.join(" · ")
                        : "No sources"}
                    </span>

                    <span>
                      <span className="material-symbols-outlined">
                        smart_toy
                      </span>
                      {botConfigsMap[event.primary_bot_config_id]?.name ||
                        "No bot"}
                    </span>

                    <span>
                      <span className="material-symbols-outlined">group</span>
                      {event.total_leads ?? 0} leads
                    </span>

                    <span>
                      <span className="material-symbols-outlined">
                        calendar_today
                      </span>
                      {formatDate(event.created_at)}
                    </span>
                  </div>
                </div>
              </div>

              {/* Right side actions */}
              <div className="admin-client-events__actions">
                <button
                  type="button"
                  className="admin-client-events__action admin-client-events__action--edit"
                  title="Edit Event"
                  onClick={() => setEditingEventId(event.id)}
                >
                  <span className="material-symbols-outlined">edit</span>
                </button>

                <button
                  type="button"
                  className="admin-client-events__action admin-client-events__action--delete"
                  title="Delete Event"
                  disabled={deletingEventId === event.id}
                  onClick={() => handleDeleteEvent(event)}
                >
                  <span className="material-symbols-outlined">delete</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      {editingEventId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="relative w-full max-w-6xl max-h-[90vh] overflow-y-auto rounded-xl bg-surface dark:bg-[#111318] shadow-2xl">
            <button
              type="button"
              onClick={() => setEditingEventId(null)}
              className="absolute right-4 top-4 z-10 w-9 h-9 rounded-full flex items-center justify-center bg-surface-container dark:bg-[#2A345E] text-on-surface dark:text-molten-text hover:opacity-80"
              aria-label="Close"
            >
              <span className="material-symbols-outlined">close</span>
            </button>

            <div className="p-6">
              <AdminCreateEvent
                eventId={editingEventId}
                event={events.find((item) => item.id === editingEventId)}
                onClose={() => setEditingEventId(null)}
                onSaved={() => {
                  setEditingEventId(null);
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
