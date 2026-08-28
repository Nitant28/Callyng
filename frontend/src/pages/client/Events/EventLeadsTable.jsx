import { useState } from "react";
import clientApi from "../../../api/client";
import LeadDrawer from "../LeadSheet/LeadDrawer";
import Modal from "../../../components/enterprise/Modal/Modal";
import Button from "../../../components/enterprise/Button/Button";
import "./EventLeadsTable.css";

const formatDateTime = (dateTime) => {
  if (!dateTime) {
    return "—";
  }

  const date = new Date(dateTime);

  if (Number.isNaN(date.getTime())) {
    return "—";
  }

  return date.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
};

const getScheduledDisplay = (lead) => {
  if (!lead?.next_attempt_at) {
    return {
      text: "—",
      isReady: false,
    };
  }

  if (
    lead.status !== "pending" &&
    lead.status !== "callback_scheduled" &&
    lead.status !== "bot_follow_up"
  ) {
    return {
      text: "—",
      isReady: false,
    };
  }

  const target = new Date(lead.next_attempt_at).getTime();

  if (Number.isNaN(target)) {
    return {
      text: "—",
      isReady: false,
    };
  }

  /*
   * Once the scheduled time has passed, the lead is ready
   * for the dialer, so don't show the old timestamp.
   */
  if (target <= Date.now()) {
    return {
      text: "—",
      isReady: false,
    };
  }

  return {
    text: formatDateTime(lead.next_attempt_at),
    isReady: false,
  };
};

const mapEventLead = (lead) => ({
  id: lead.id,
  sessionCallId: lead.session_call_id || null,
  name: lead.name || null,
  phone: lead.phone || null,
  email: lead.email || null,
  status: lead.status || null,
  outcome: lead.outcome || null,
  attempts: lead.attempts ?? 0,
  lastCallDurationSeconds: lead.last_call_duration_seconds ?? 0,
  campaignName: "—",
  lastCalledAt: lead.last_attempted_at || lead.created_at || null,
  updatedAt: lead.last_attempted_at || lead.created_at || null,
});
const EventLeadsTable = ({
  leads = [],
  leadsLoading = false,
  totalLeadsCount = 0,
  eventId,
  onLeadsChanged,
}) => {
  const [selectedLead, setSelectedLead] = useState(null);
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);
  const [drawerLead, setDrawerLead] = useState(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const [isAddLeadOpen, setIsAddLeadOpen] = useState(false);

  const [isEditLeadOpen, setIsEditLeadOpen] = useState(false);
  const [editLeadData, setEditLeadData] = useState(null);
  const [editError, setEditError] = useState("");
  const [isSavingEdit, setIsSavingEdit] = useState(false);
  const [newLead, setNewLead] = useState({
    name: "",
    phone: "",
    email: "",
  });
  const filteredLeads = leads.filter((lead) => {
    const query = searchQuery.trim().toLowerCase();

    const matchesSearch =
      !query ||
      (lead.name || "").toLowerCase().includes(query) ||
      (lead.phone || "").toLowerCase().includes(query) ||
      (lead.email || "").toLowerCase().includes(query);

    const matchesStatus =
      statusFilter === "all" ||
      (lead.status || "").toLowerCase() === statusFilter;

    return matchesSearch && matchesStatus;
  });

  const handleDelete = async (lead) => {
    const confirmed = window.confirm(`Delete ${lead.name || lead.phone}?`);

    if (!confirmed) {
      return;
    }

    try {
      await clientApi.delete(`/api/events/${eventId}/leads/${lead.id}`);

      await onLeadsChanged?.();
    } catch (err) {
      console.error("Failed to delete event lead:", err);

      window.alert(err.response?.data?.detail || "Failed to delete lead.");
    }
  };

  const handleAddLead = async (e) => {
    e.preventDefault();

    if (!newLead.phone.trim()) {
      window.alert("Phone number is required.");
      return;
    }

    try {
      await clientApi.post(`/api/events/${eventId}/leads`, {
        phone: newLead.phone.trim(),
        name: newLead.name.trim() || null,
        email: newLead.email.trim() || null,
        metadata: null,
      });

      setIsAddLeadOpen(false);

      setNewLead({
        name: "",
        phone: "",
        email: "",
      });

      await onLeadsChanged?.();
    } catch (err) {
      console.error("Failed to add event lead:", err);

      window.alert(err.response?.data?.detail || "Failed to add lead.");
    }
  };
  const handleEditLead = async (e) => {
    e?.preventDefault?.();

    if (!editLeadData) {
      return;
    }

    if (!editLeadData.name?.trim()) {
      setEditError("Name is required.");
      return;
    }

    if (!editLeadData.phone?.trim()) {
      setEditError("Phone number is required.");
      return;
    }

    setEditError("");
    setIsSavingEdit(true);

    try {
      await clientApi.patch(`/api/events/${eventId}/leads/${editLeadData.id}`, {
        name: editLeadData.name.trim(),
        phone: editLeadData.phone.trim(),
        status: editLeadData.status,
      });

      setIsEditLeadOpen(false);
      setEditLeadData(null);

      await onLeadsChanged?.();
    } catch (err) {
      console.error("Failed to edit event lead:", err);

      setEditError(err.response?.data?.detail || "Failed to update lead.");
    } finally {
      setIsSavingEdit(false);
    }
  };
  return (
    <div className="event-leads">
      <div className="event-leads__toolbar">
        <div className="event-leads__filters">
          <input
            type="text"
            className="event-leads__search"
            placeholder="Search name, phone or email..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />

          <select
            className="event-leads__status-filter"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="all">All Statuses</option>
            <option value="pending">Pending</option>
            <option value="calling">Calling</option>
            <option value="bot_follow_up">Bot Follow Up</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="callback_scheduled">Callback</option>
          </select>
        </div>

        <button
          type="button"
          className="event-leads__add-button"
          onClick={() => setIsAddLeadOpen(true)}
        >
          + Add Lead
        </button>
      </div>

      <div className="event-leads__summary">
        Showing {filteredLeads.length} of {totalLeadsCount} leads
      </div>

      <div className="event-leads__table-wrap">
        <table className="event-leads__table">
          <thead>
            <tr>
              <th>Lead</th>
              <th>Phone</th>
              <th>Status</th>
              <th>Scheduled</th>
              <th>Outcome</th>
              <th>Attempts</th>
              <th>Last Call</th>
              <th>Duration</th>
              <th>Actions</th>
            </tr>
          </thead>

          <tbody>
            {leadsLoading ? (
              <tr>
                <td colSpan={9}>Loading leads...</td>
              </tr>
            ) : filteredLeads.length === 0 ? (
              <tr>
                <td colSpan={9}>
                  {leads.length === 0
                    ? "No leads found"
                    : "No leads match your filters."}
                </td>
              </tr>
            ) : (
              filteredLeads.map((lead) => {
                const scheduled = getScheduledDisplay(lead);

                const statusClass = (lead.status || "")
                  .toLowerCase()
                  .replace(/_/g, "-");

                const outcomeClass = (lead.outcome || "")
                  .toLowerCase()
                  .replace(/_/g, "-")
                  .replace(/\s+/g, "-");
                return (
                  <tr key={lead.id}>
                    <td>{lead.name || "—"}</td>

                    <td>{lead.phone || "—"}</td>

                    <td>
                      <span
                        className={`event-leads__status event-leads__status--${statusClass}`}
                      >
                        {lead.status || "—"}
                      </span>
                    </td>

                    <td>
                      <span
                        className={`event-leads__scheduled ${
                          scheduled.isReady
                            ? "event-leads__scheduled--ready"
                            : "event-leads__scheduled--waiting"
                        }`}
                      >
                        {scheduled.text}
                      </span>
                    </td>

                    <td>
                      <span
                        className={`event-leads__outcome ${
                          outcomeClass
                            ? `event-leads__outcome--${outcomeClass}`
                            : ""
                        }`}
                      >
                        {lead.outcome || "—"}
                      </span>
                    </td>

                    <td>
                      <span className="event-leads__attempts">
                        {lead.attempts || 0}
                      </span>
                    </td>

                    <td>
                      <span className="event-leads__last-call">
                        {formatDateTime(lead.last_attempted_at)}
                      </span>
                    </td>

                    <td>
                      <span className="event-leads__duration">
                        {lead.last_call_duration_seconds || 0}s
                      </span>
                    </td>

                    <td className="event-leads__actions">
                      <button
                        type="button"
                        className="event-leads__action-button event-leads__action-button--icon"
                        onClick={() => {
                          setEditError("");

                          setEditLeadData({
                            ...lead,
                            original_status: lead.status,
                          });

                          setIsEditLeadOpen(true);
                        }}
                        title="Edit lead"
                        aria-label="Edit lead"
                      >
                        <span className="material-symbols-outlined">edit</span>
                      </button>

                      <button
                        type="button"
                        className="event-leads__action-button event-leads__action-button--icon event-leads__action-button--danger"
                        onClick={() => handleDelete(lead)}
                        title="Delete lead"
                        aria-label="Delete lead"
                      >
                        <span className="material-symbols-outlined">
                          delete
                        </span>
                      </button>

                      <button
                        type="button"
                        className="event-leads__action-button event-leads__action-button--details"
                        onClick={() => {
                          setDrawerLead(mapEventLead(lead));
                          setIsDetailsOpen(true);
                        }}
                      >
                        Details
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {isDetailsOpen && drawerLead && (
        <LeadDrawer
          open={isDetailsOpen}
          lead={drawerLead}
          onClose={() => {
            setIsDetailsOpen(false);
            setDrawerLead(null);
          }}
        />
      )}

      {isAddLeadOpen && (
        <Modal
          open={isAddLeadOpen}
          onClose={() => setIsAddLeadOpen(false)}
          title="Add Lead"
          subtitle="Add a new lead to this event."
          icon="person_add"
          width={480}
          footer={
            <>
              <Button variant="ghost" onClick={() => setIsAddLeadOpen(false)}>
                Cancel
              </Button>

              <Button variant="primary" onClick={handleAddLead}>
                Add Lead
              </Button>
            </>
          }
        >
          <form className="ent-form" onSubmit={handleAddLead}>
            {/* Name */}
            <label>
              Full Name
              <input
                type="text"
                value={newLead.name}
                onChange={(e) =>
                  setNewLead({
                    ...newLead,
                    name: e.target.value,
                  })
                }
                placeholder="e.g. Rahul Patil"
              />
            </label>

            {/* Phone */}
            <label>
              Phone Number (with prefix)
              <input
                type="tel"
                value={newLead.phone}
                onChange={(e) =>
                  setNewLead({
                    ...newLead,
                    phone: e.target.value,
                  })
                }
                placeholder="e.g. 919876543210"
                required
              />
            </label>

            {/* Email */}
            <label>
              Email
              <input
                type="email"
                value={newLead.email}
                onChange={(e) =>
                  setNewLead({
                    ...newLead,
                    email: e.target.value,
                  })
                }
                placeholder="e.g. rahul@example.com"
              />
            </label>
          </form>
        </Modal>
      )}
      <Modal
        open={isEditLeadOpen && Boolean(editLeadData)}
        onClose={() => {
          if (isSavingEdit) return;

          setIsEditLeadOpen(false);
          setEditLeadData(null);
          setEditError("");
        }}
        title="Edit Lead"
        subtitle="Modify lead details and manual status settings."
        icon="edit"
        width={480}
        footer={
          <>
            <Button
              variant="ghost"
              disabled={isSavingEdit}
              onClick={() => {
                setIsEditLeadOpen(false);
                setEditLeadData(null);
                setEditError("");
              }}
            >
              Cancel
            </Button>

            <Button
              variant="primary"
              disabled={isSavingEdit}
              onClick={handleEditLead}
            >
              {isSavingEdit ? "Saving..." : "Save Changes"}
            </Button>
          </>
        }
      >
        {editLeadData && (
          <form className="ent-form" onSubmit={handleEditLead}>
            <label>
              Full Name
              <input
                type="text"
                value={editLeadData.name || ""}
                onChange={(e) =>
                  setEditLeadData({
                    ...editLeadData,
                    name: e.target.value,
                  })
                }
                placeholder="e.g. Rahul Patil"
                required
              />
            </label>

            <label>
              Phone Number (with prefix)
              <input
                type="tel"
                value={editLeadData.phone || ""}
                onChange={(e) =>
                  setEditLeadData({
                    ...editLeadData,
                    phone: e.target.value,
                  })
                }
                placeholder="e.g. 919876543210"
                required
              />
            </label>

            <label>
              Status
              <select
                value={editLeadData.status || "pending"}
                onChange={(e) =>
                  setEditLeadData({
                    ...editLeadData,
                    status: e.target.value,
                  })
                }
              >
                <option value="pending">Pending</option>

                <option value="callback_scheduled">Callback Scheduled</option>

                <option value="bot_follow_up">Bot Follow Up</option>

                <option value="completed">Completed</option>

                <option value="failed">Failed</option>
              </select>
            </label>

            {editError && <p className="ent-form__error">{editError}</p>}
          </form>
        )}
      </Modal>
    </div>
  );
};

export default EventLeadsTable;
