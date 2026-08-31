import React, { useEffect, useMemo, useState } from "react";
import "./AdminEvents.css";
import { useNavigate } from "react-router-dom";
import adminApi from "../../shared/api/admin";
import { useAdminData } from "../contexts/AdminDataContext";

export default function AdminEvents() {
  const [search, setSearch] = useState("");
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const navigate = useNavigate();
  const { clientsMap } = useAdminData();

  useEffect(() => {
    const fetchEvents = async () => {
      try {
        setLoading(true);
        setError("");

        const res = await adminApi.get("/internal/events");

        setEvents(res.data?.events || []);
      } catch (err) {
        console.error("Failed to fetch events:", err);
        setError("Failed to load events.");
      } finally {
        setLoading(false);
      }
    };

    fetchEvents();
  }, []);

  /*
   * Build client list from events.
   *
   * Only clients that have at least one event
   * will appear on this page.
   */
  const clientsWithEvents = useMemo(() => {
    const grouped = {};

    events.forEach((event) => {
      const clientId = event.client_id;

      if (!clientId) {
        return;
      }

      if (!grouped[clientId]) {
        grouped[clientId] = {
          clientId,
          clientName:
            clientsMap[clientId]?.name || event.client_name || "Unknown Client",
          events: [],
        };
      }

      grouped[clientId].events.push(event);
    });

    return Object.values(grouped).map((client) => {
      const clientEvents = client.events;

      const activeEvents = clientEvents.filter(
        (event) => event.status === "active",
      ).length;

      const latestEvent = [...clientEvents].sort((a, b) => {
        const dateA = new Date(a.created_at || 0).getTime();
        const dateB = new Date(b.created_at || 0).getTime();

        return dateB - dateA;
      })[0];

      const totalLeads = clientEvents.reduce(
        (sum, event) => sum + Number(event.total_leads || 0),
        0,
      );

      return {
        ...client,
        eventCount: clientEvents.length,
        activeEvents,
        totalLeads,
        latestEventDate: latestEvent?.created_at || null,
      };
    });
  }, [events, clientsMap]);

  const filteredClients = useMemo(() => {
    const query = search.trim().toLowerCase();

    if (!query) {
      return clientsWithEvents;
    }

    return clientsWithEvents.filter((client) =>
      client.clientName.toLowerCase().includes(query),
    );
  }, [clientsWithEvents, search]);

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

  const getInitials = (name) => {
    if (!name) {
      return "?";
    }

    const words = name.trim().split(/\s+/);

    if (words.length === 1) {
      return words[0].slice(0, 2).toUpperCase();
    }

    return `${words[0][0]}${words[1][0]}`.toUpperCase();
  };

  return (
    <div className="admin-page events-page">
      {/* =====================================================
          Header
          ===================================================== */}
      <div className="admin-page__header events-page__header">
        <div>
          <div className="events-page__eyebrow">
            <span className="material-symbols-outlined">hub</span>
            AI CALLING WORKFLOWS
          </div>

          <h1 className="admin-page__title">Events</h1>

          <p className="admin-page__subtitle">
            Manage client events, lead sources, and AI calling workflows.
          </p>
        </div>

        <button
          type="button"
          className="admin-button admin-button--primary"
          onClick={() => navigate("/admin/events/create")}
        >
          <span className="material-symbols-outlined">add</span>
          Create Event
        </button>
      </div>

      {/* =====================================================
          Search
          ===================================================== */}
      <div className="admin-card events-toolbar">
        <div className="events-toolbar__search">
          <span className="material-symbols-outlined">search</span>

          <input
            type="text"
            placeholder="Search clients..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />

          {search && (
            <button
              type="button"
              className="events-toolbar__clear"
              onClick={() => setSearch("")}
              aria-label="Clear search"
            >
              <span className="material-symbols-outlined">close</span>
            </button>
          )}
        </div>

        <div className="events-toolbar__count">
          <span className="material-symbols-outlined">groups</span>
          {filteredClients.length}{" "}
          {filteredClients.length === 1 ? "client" : "clients"}
        </div>
      </div>

      {/* =====================================================
          Clients
          ===================================================== */}
      <div className="admin-card events-table-card">
        <div className="events-table-card__header">
          <div>
            <div className="events-table-card__title-row">
              <h2>Clients</h2>

              <span className="events-table-card__count">
                {clientsWithEvents.length}
              </span>
            </div>

            <span>
              Clients with configured events and AI calling workflows.
            </span>
          </div>
        </div>

        {loading ? (
          <div className="events-empty">
            <div className="events-empty__icon events-empty__icon--loading">
              <span className="material-symbols-outlined">sync</span>
            </div>

            <h3>Loading clients...</h3>

            <p>Fetching event configurations.</p>
          </div>
        ) : error ? (
          <div className="events-empty">
            <div className="events-empty__icon events-empty__icon--error">
              <span className="material-symbols-outlined">error</span>
            </div>

            <h3>Unable to load events</h3>

            <p>{error}</p>
          </div>
        ) : filteredClients.length === 0 ? (
          <div className="events-empty">
            <div className="events-empty__icon">
              <span className="material-symbols-outlined">
                {search ? "search_off" : "event"}
              </span>
            </div>

            <h3>{search ? "No clients found" : "No events yet"}</h3>

            <p>
              {search
                ? "Try searching with a different client name."
                : "Create an event to start managing AI calling workflows."}
            </p>

            {!search && (
              <button
                type="button"
                className="admin-button admin-button--primary"
                onClick={() => navigate("/admin/events/create")}
              >
                <span className="material-symbols-outlined">add</span>
                Create Event
              </button>
            )}
          </div>
        ) : (
          <div className="events-client-list">
            {filteredClients.map((client) => (
              <button
                key={client.clientId}
                type="button"
                className="events-client-row"
                onClick={() =>
                  navigate(`/admin/events/${client.clientId}`)
                }
              >
                {/* Client */}
                <div className="events-client-row__client">
                  <div className="events-client-row__avatar">
                    {getInitials(client.clientName)}
                  </div>

                  <div className="events-client-row__client-info">
                    <strong>{client.clientName}</strong>

                    <span>
                      <span className="material-symbols-outlined">
                        fingerprint
                      </span>
                      Client workspace
                    </span>
                  </div>
                </div>

                {/* Event count */}
                <div className="events-client-row__metric">
                  <span className="events-client-row__metric-label">
                    Events
                  </span>

                  <strong>{client.eventCount}</strong>
                </div>

                {/* Active */}
                <div className="events-client-row__metric">
                  <span className="events-client-row__metric-label">
                    Active
                  </span>

                  <strong className="events-client-row__active">
                    {client.activeEvents}
                  </strong>
                </div>

                {/* Leads */}
                <div className="events-client-row__metric">
                  <span className="events-client-row__metric-label">
                    Leads
                  </span>

                  <strong>{client.totalLeads}</strong>
                </div>

                {/* Last created */}
                <div className="events-client-row__date">
                  <span className="events-client-row__metric-label">
                    Latest event
                  </span>

                  <strong>{formatDate(client.latestEventDate)}</strong>
                </div>

                {/* Arrow */}
                <div className="events-client-row__arrow">
                  <span className="material-symbols-outlined">
                    arrow_forward
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}