import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import clientApi from "../../../api/client";
import "./EventsPage.css";

const PAGE_SIZE = 25;

const EventsPage = () => {
  const navigate = useNavigate();

  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("newest");
  const [page, setPage] = useState(0);

  const loadEvents = async (showRefreshing = false) => {
    try {
      if (showRefreshing) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      setError("");

      const response = await clientApi.get("/api/events", {
        params: {
          limit: 500,
          offset: 0,
        },
      });

      setEvents(response.data?.events || []);
    } catch (err) {
      console.error("Failed to load events:", err);

      setError(
        err?.response?.data?.detail || err?.message || "Failed to load events.",
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadEvents();
  }, []);

  const filteredEvents = useMemo(() => {
    let result = [...events];

    if (search.trim()) {
      const query = search.trim().toLowerCase();

      result = result.filter((event) =>
        (event.name || "").toLowerCase().includes(query),
      );
    }

    result.sort((a, b) => {
      if (sortBy === "oldest") {
        return (
          new Date(a.created_at || 0).getTime() -
          new Date(b.created_at || 0).getTime()
        );
      }

      if (sortBy === "name") {
        return (a.name || "").localeCompare(b.name || "");
      }

      return (
        new Date(b.created_at || 0).getTime() -
        new Date(a.created_at || 0).getTime()
      );
    });

    return result;
  }, [events, search, sortBy]);

  const totalPages = Math.max(1, Math.ceil(filteredEvents.length / PAGE_SIZE));

  const pagedEvents = filteredEvents.slice(
    page * PAGE_SIZE,
    page * PAGE_SIZE + PAGE_SIZE,
  );

  const handleSearchChange = (value) => {
    setSearch(value);
    setPage(0);
  };

  const getStatusLabel = (value) => {
    if (!value) return "—";

    return value.charAt(0).toUpperCase() + value.slice(1);
  };

  const getStatusClass = (value) => {
    if (value === "active") {
      return "event-status event-status--active";
    }

    return "event-status";
  };

  return (
    <div className="cl-page-container app-page events-page">
      {/* Header */}
      <div className="events-page__header">
        <div>
          <h1 className="events-page__title">Events</h1>

          <p className="events-page__subtitle">
            Manage your events and view their leads and calling activity.
          </p>
        </div>

        <button
          type="button"
          className="events-refresh-button"
          onClick={() => loadEvents(true)}
          disabled={refreshing}
        >
          <span className="material-symbols-outlined">refresh</span>

          {refreshing ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {/* Error */}
      {error && <div className="events-error">{error}</div>}

      {/* Toolbar */}
      <div className="events-toolbar">
        <div className="events-toolbar__search">
          <span className="material-symbols-outlined">search</span>

          <input
            type="text"
            placeholder="Search events..."
            value={search}
            onChange={(e) => handleSearchChange(e.target.value)}
          />
        </div>

        <select
          className="events-toolbar__select"
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
        >
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
          <option value="name">Name</option>
        </select>
      </div>

      {/* Events */}
      <div className="events-card">
        <div className="events-card__header">
          <div>
            <h2>All Events</h2>
            <span>
              {filteredEvents.length} event
              {filteredEvents.length !== 1 ? "s" : ""}
            </span>
          </div>
        </div>

        {loading ? (
          <div className="events-loading">Loading events...</div>
        ) : pagedEvents.length === 0 ? (
          <div className="events-empty">
            <div className="events-empty__icon">
              <span className="material-symbols-outlined">event</span>
            </div>

            <h3>No events found</h3>

            <p>There are no events matching your current filters.</p>
          </div>
        ) : (
          <div className="events-table-wrapper">
            <table className="events-table">
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Status</th>
                  <th>Lead Sources</th>
                  <th>Leads</th>
                  <th>Created</th>
                  <th />
                </tr>
              </thead>

              <tbody>
                {pagedEvents.map((event) => (
                  <tr key={event.id}>
                    <td>
                      <div className="event-name-cell">
                        <div className="event-name">
                          {event.name || "Untitled Event"}
                        </div>

                        {event.description && (
                          <div className="event-description">
                            {event.description}
                          </div>
                        )}
                      </div>
                    </td>

                    <td>
                      <span className={getStatusClass(event.status)}>
                        {getStatusLabel(event.status)}
                      </span>
                    </td>

                    <td>
                      {event.source_types?.length
                        ? event.source_types.join(", ")
                        : "—"}
                    </td>

                    <td>{event.total_leads ?? 0}</td>

                    <td>
                      {event.created_at
                        ? new Date(event.created_at).toLocaleDateString("en-IN")
                        : "—"}
                    </td>

                    <td>
                      <button
                        type="button"
                        className="event-open-button"
                        // onClick={() =>
                        //   navigate(`/app/events/${event.id}`)
                        // }
                        onClick={() => {
                          navigate(`/app/events/${event.id}`);
                        }}
                      >
                        View
                        <span className="material-symbols-outlined">
                          chevron_right
                        </span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {!loading && filteredEvents.length > PAGE_SIZE && (
          <div className="events-pagination">
            <button
              type="button"
              disabled={page === 0}
              onClick={() => setPage((current) => Math.max(0, current - 1))}
            >
              Previous
            </button>

            <span>
              Page {page + 1} of {totalPages}
            </span>

            <button
              type="button"
              disabled={page >= totalPages - 1}
              onClick={() =>
                setPage((current) => Math.min(totalPages - 1, current + 1))
              }
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default EventsPage;
