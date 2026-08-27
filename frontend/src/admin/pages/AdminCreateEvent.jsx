import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAdminData } from "../contexts/AdminDataContext";
import adminApi from "../../shared/api/admin";

export default function AdminCreateEvent({
  eventId = null,
  event = null,
  onClose = null,
  onSaved = null,
}) {
  const navigate = useNavigate();
  const { clients, botConfigs } = useAdminData();
  const isEditMode = Boolean(eventId);

  const [formData, setFormData] = useState({
    name: "",
    client_id: "",
    description: "",
    source_types: [],
    primary_bot_id: "",

    initial_call_delay_minutes: 0,
    max_attempts: 3,
    retry_delay_minutes: 30,

    lead_handling: "",
  });

  const [currentStep, setCurrentStep] = useState(0);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState("");

  const [showOutcomeConfig, setShowOutcomeConfig] = useState(false);
  const [outcomes, setOutcomes] = useState([]);
  const [outcomeBotMappings, setOutcomeBotMappings] = useState({});
  const [isLoadingOutcomes, setIsLoadingOutcomes] = useState(false);

  useEffect(() => {
    if (!eventId || !event) return;

    setFormData({
      name: event.name || "",
      client_id: event.client_id || "",
      description: event.description || "",
      source_types: event.source_types || [],
      primary_bot_id: event.primary_bot_config_id || "",

      initial_call_delay_minutes: event.attempt_0_schedule_minutes ?? 0,

      max_attempts: event.max_attempts ?? 3,

      retry_delay_minutes:
        event.attempt_1_schedule_minutes != null &&
        event.attempt_0_schedule_minutes != null
          ? event.attempt_1_schedule_minutes - event.attempt_0_schedule_minutes
          : 30,

      lead_handling: event.lead_handling || "",
    });

    setCurrentStep(0);
    setError("");
  }, [eventId, event]);

  const handleChange = (field, value) => {
    setFormData((prev) => ({
      ...prev,
      [field]: value,
    }));

    if (error) {
      setError("");
    }
  };

  const handleContinue = () => {
    if (currentStep < 4) {
      setCurrentStep((prev) => prev + 1);
    }
  };

  const handleConfigureOutcomes = async () => {
    if (!formData.primary_bot_id || !formData.client_id) {
      return;
    }

    setIsLoadingOutcomes(true);
    setError("");

    try {
      const response = await adminApi.get(
        `/internal/bot-configs/${formData.primary_bot_id}/outcomes`,
        {
          params: {
            client_id: formData.client_id,
          },
        },
      );

      const fetchedOutcomes = response.data?.outcomes || [];

      setOutcomes(fetchedOutcomes);

      // Preserve existing selections and initialize new outcomes.
      setOutcomeBotMappings((prev) => {
        const next = {};

        fetchedOutcomes.forEach((outcome) => {
          next[outcome] = prev[outcome] || "";
        });

        return next;
      });

      setShowOutcomeConfig(true);
    } catch (err) {
      console.error("Failed to load bot outcomes:", err);

      setError(
        err?.response?.data?.detail ||
          "Failed to load outcomes for the selected bot.",
      );
    } finally {
      setIsLoadingOutcomes(false);
    }
  };
  /**
   * Get authentication token.
   *
   * IMPORTANT:
   * Replace this key if your AdminAuthContext stores the token
   * under a different localStorage key.
   */

  /**
   * Create event using:
   *
   * POST /api/events
   *
   * Backend expects:
   * {
   *   name,
   *   description,
   *   source_type,
   *   primary_bot_config_id,
   *   max_concurrent_calls,
   *   calls_per_minute,
   *   max_attempts,
   *   attempt_0_schedule_minutes,
   *   attempt_1_schedule_minutes,
   *   attempt_2_schedule_minutes
   * }
   */
  const handleSaveEvent = async () => {
    setError("");

    if (!formData.name.trim()) {
      setError("Event name is required.");
      setCurrentStep(0);
      return;
    }

    if (!formData.client_id) {
      setError("Please select a client.");
      setCurrentStep(0);
      return;
    }

    if (!formData.source_types.length) {
      setError("Please select a lead source.");
      setCurrentStep(1);
      return;
    }

    if (!formData.primary_bot_id) {
      setError("Please select a primary bot.");
      setCurrentStep(2);
      return;
    }

    if (!formData.lead_handling) {
      setError("Please select lead handling.");
      setCurrentStep(0);
      return;
    }

    setIsCreating(true);

    try {
      const initialDelay = Number(formData.initial_call_delay_minutes || 0);

      const retryDelay = Number(formData.retry_delay_minutes || 0);

      const attempt0Schedule = initialDelay;
      const attempt1Schedule = initialDelay + retryDelay;
      const attempt2Schedule = initialDelay + retryDelay * 2;

      const payload = {
        client_id: formData.client_id,
        name: formData.name.trim(),
        description: formData.description.trim() || null,
        source_types: formData.source_types,
        lead_handling: formData.lead_handling,
        primary_bot_config_id: formData.primary_bot_id,

        max_concurrent_calls: 5,
        calls_per_minute: 10,
        max_attempts: Number(formData.max_attempts),

        attempt_0_schedule_minutes: attempt0Schedule,

        attempt_1_schedule_minutes:
          Number(formData.max_attempts) >= 2 ? attempt1Schedule : null,

        attempt_2_schedule_minutes:
          Number(formData.max_attempts) >= 3 ? attempt2Schedule : null,
      };

      let savedEventId;

      if (isEditMode) {
        // EDIT
        const response = await adminApi.patch(
          `/internal/events/${eventId}`,
          payload,
        );

        savedEventId = response.data?.event?.id || response.data?.id || eventId;

        console.log("Event updated successfully:", response.data);
      } else {
        // CREATE
        const response = await adminApi.post("/internal/events", payload);

        savedEventId = response.data?.event?.id || response.data?.id;

        if (!savedEventId) {
          throw new Error("Event was created but no event ID was returned.");
        }

        console.log("Event created successfully:", response.data);
      }

      // Save outcome → bot mappings
      for (const outcome of outcomes) {
        const botConfigId = outcomeBotMappings[outcome];

        if (!botConfigId) {
          continue;
        }

        await adminApi.post(`/internal/events/${savedEventId}/outcomes`, {
          outcome,
          bot_config_id: botConfigId,
        });
      }

      console.log(
        isEditMode
          ? "Event updated successfully."
          : "Event created successfully.",
      );

      if (onSaved) {
        onSaved();
      } else {
        navigate("/admin/events");
      }
    } catch (err) {
      console.error(
        isEditMode ? "Update event error:" : "Create event error:",
        err,
      );

      setError(
        err?.response?.data?.detail ||
          err?.message ||
          (isEditMode
            ? "Something went wrong while updating the event."
            : "Something went wrong while creating the event."),
      );
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="w-full">
      {/* Header */}
      <div className="flex flex-col mb-stack-lg">
        <h2 className="font-headline-lg text-headline-lg text-on-surface dark:text-molten-text">
          Create Event
        </h2>

        <p className="font-body-md text-body-md text-arctic-text-muted dark:text-molten-text-muted mt-1">
          Configure a new event and its lead calling workflow.
        </p>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-6 rounded-lg border border-red-300 dark:border-red-900 bg-red-50 dark:bg-red-950/30 px-4 py-3">
          <div className="flex items-start gap-3">
            <span className="material-symbols-outlined text-red-600 dark:text-red-400">
              error
            </span>

            <div>
              <p className="text-sm font-medium text-red-700 dark:text-red-300">
                Unable to create event
              </p>

              <p className="text-sm text-red-600 dark:text-red-400 mt-1">
                {error}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Event Creation Steps */}
      <div className="mb-6 border-b border-outline-variant dark:border-[#2A345E]">
        <div className="flex items-center gap-8 overflow-x-auto">
          {[
            { label: "Event Details", index: 0 },
            { label: "Lead Source", index: 1 },
            { label: "Bot Configuration", index: 2 },
            { label: "Schedule & Attempts", index: 3 },
            { label: "Review", index: 4 },
          ].map((step) => {
            const isActive = currentStep === step.index;
            const isCompleted = currentStep > step.index;

            return (
              <button
                key={step.index}
                type="button"
                onClick={() => setCurrentStep(step.index)}
                className={`
                  relative flex items-center gap-2
                  pb-3
                  whitespace-nowrap
                  text-sm font-medium
                  transition-colors
                  ${
                    isActive
                      ? "text-primary dark:text-molten-primary"
                      : isCompleted
                        ? "text-on-surface dark:text-molten-text"
                        : "text-on-surface-variant dark:text-molten-text-muted"
                  }
                `}
              >
                <span
                  className={`
                    flex items-center justify-center
                    w-6 h-6
                    rounded-full
                    text-xs
                    ${
                      isActive
                        ? "bg-primary dark:bg-molten-primary text-on-primary"
                        : isCompleted
                          ? "bg-primary/10 dark:bg-molten-primary/10 text-primary dark:text-molten-primary"
                          : "bg-surface-container dark:bg-[#2A345E] text-on-surface-variant dark:text-molten-text-muted"
                    }
                  `}
                >
                  {isCompleted ? (
                    <span className="material-symbols-outlined text-[16px]">
                      check
                    </span>
                  ) : (
                    step.index + 1
                  )}
                </span>

                <span>{step.label}</span>

                {isActive && (
                  <span className="absolute bottom-0 left-0 right-0 h-[2px] bg-primary dark:bg-molten-primary" />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* ========================================================= */}
      {/* STEP 0 - EVENT DETAILS */}
      {/* ========================================================= */}

      {currentStep === 0 && (
        <div className="bg-surface-container-lowest dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-lg overflow-hidden">
          <div className="p-6 border-b border-outline-variant dark:border-[#2A345E] bg-surface-container-low dark:bg-[#1A1C24]">
            <h3 className="font-headline-sm text-on-surface dark:text-molten-text">
              Event Details
            </h3>

            <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mt-1">
              Basic information about this event.
            </p>
          </div>

          <div className="p-6 space-y-6">
            {/* Event Name */}
            <div>
              <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">
                Event Name
              </label>

              <input
                required
                type="text"
                value={formData.name}
                onChange={(e) => handleChange("name", e.target.value)}
                placeholder="e.g. Pune Property Expo"
                className="w-full p-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary"
              />
            </div>

            {/* Client */}
            <div>
              <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">
                Client
              </label>

              <select
                required
                value={formData.client_id}
                onChange={(e) => handleChange("client_id", e.target.value)}
                className="w-full p-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary"
              >
                <option value="">Select a client</option>

                {clients.map((client) => (
                  <option key={client.id} value={client.id}>
                    {client.name}
                  </option>
                ))}
              </select>

              <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mt-1">
                The selected client is currently used for UI selection. The
                current /api/events backend derives the client from the
                authenticated token.
              </p>
            </div>

            {/* Description */}
            <div>
              <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">
                Description
              </label>

              <textarea
                rows={4}
                value={formData.description}
                onChange={(e) => handleChange("description", e.target.value)}
                placeholder="Describe the purpose of this event..."
                className="w-full p-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary resize-y"
              />
            </div>

            {/* Lead Handling */}
            <div className="mt-6">
              <label className="block text-sm font-medium text-on-surface dark:text-molten-text mb-1">
                Lead Handling
              </label>

              <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mb-3">
                Choose what should happen when the lead requires further
                attention.
              </p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Follow Up */}
                <label
                  className={`flex items-start gap-3 p-4 rounded-lg border cursor-pointer transition-colors ${
                    formData.lead_handling === "follow_up"
                      ? "border-primary dark:border-molten-primary bg-primary/5 dark:bg-molten-primary/5"
                      : "border-outline-variant dark:border-[#2A345E]"
                  }`}
                >
                  <input
                    type="radio"
                    name="lead_handling"
                    value="follow_up"
                    checked={formData.lead_handling === "follow_up"}
                    onChange={(e) =>
                      handleChange("lead_handling", e.target.value)
                    }
                    className="mt-1"
                  />

                  <div>
                    <p className="text-sm font-medium text-on-surface dark:text-molten-text">
                      Follow Up
                    </p>

                    <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mt-1">
                      Continue the lead workflow with follow-up attempts.
                    </p>
                  </div>
                </label>

                {/* Handover */}
                <label
                  className={`flex items-start gap-3 p-4 rounded-lg border cursor-pointer transition-colors ${
                    formData.lead_handling === "handover"
                      ? "border-primary dark:border-molten-primary bg-primary/5 dark:bg-molten-primary/5"
                      : "border-outline-variant dark:border-[#2A345E]"
                  }`}
                >
                  <input
                    type="radio"
                    name="lead_handling"
                    value="handover"
                    checked={formData.lead_handling === "handover"}
                    onChange={(e) =>
                      handleChange("lead_handling", e.target.value)
                    }
                    className="mt-1"
                  />

                  <div>
                    <p className="text-sm font-medium text-on-surface dark:text-molten-text">
                      Handover
                    </p>

                    <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mt-1">
                      Hand the lead over to the appropriate human or team
                      workflow.
                    </p>
                  </div>
                </label>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* STEP 1 - LEAD SOURCE */}
      {/* ========================================================= */}

      {currentStep === 1 && (
        <div className="bg-surface-container-lowest dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-lg overflow-hidden">
          <div className="p-6 border-b border-outline-variant dark:border-[#2A345E] bg-surface-container-low dark:bg-[#1A1C24]">
            <h3 className="font-headline-sm text-on-surface dark:text-molten-text">
              Lead Source
            </h3>

            <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mt-1">
              Choose how leads will enter this event.
            </p>
          </div>

          <div className="p-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[
                {
                  value: "file",
                  icon: "upload_file",
                  title: "CSV / Excel",
                  description: "Upload a file containing your leads.",
                },
                {
                  value: "google_sheets",
                  icon: "table_chart",
                  title: "Google Sheets",
                  description: "Import leads from a Google Sheet.",
                },
                {
                  value: "webhook",
                  icon: "webhook",
                  title: "Webhook",
                  description: "Receive leads through an HTTP webhook.",
                },
                {
                  value: "meta_ads",
                  icon: "campaign",
                  title: "Meta Ads",
                  description: "Receive leads from Meta lead ads.",
                },
                {
                  value: "google_ads",
                  icon: "ads_click",
                  title: "Google Ads",
                  description: "Receive leads from Google Ads lead forms.",
                },
                {
                  value: "manual",
                  icon: "person_add",
                  title: "Manual Entry",
                  description: "Add leads manually to this event.",
                },
              ].map((source) => (
                <button
                  key={source.value}
                  type="button"
                  onClick={() => {
                    const currentSources = formData.source_types;

                    const updatedSources = currentSources.includes(source.value)
                      ? currentSources.filter((value) => value !== source.value)
                      : [...currentSources, source.value];

                    handleChange("source_types", updatedSources);
                  }}
                  className={`text-left p-5 rounded-lg border transition-colors ${
                    formData.source_types.includes(source.value)
                      ? "border-primary dark:border-molten-primary bg-primary/5 dark:bg-molten-primary/10"
                      : "border-outline-variant dark:border-[#2A345E] hover:bg-surface-container dark:hover:bg-[#1A1C24]"
                  }`}
                >
                  <div className="flex items-start gap-4">
                    <div className="w-10 h-10 rounded-lg bg-surface-container dark:bg-[#2A345E]/50 flex items-center justify-center shrink-0">
                      <span className="material-symbols-outlined">
                        {source.icon}
                      </span>
                    </div>

                    <div>
                      <h4 className="font-medium text-on-surface dark:text-molten-text">
                        {source.title}
                      </h4>

                      <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mt-1">
                        {source.description}
                      </p>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* STEP 2 - BOT CONFIGURATION */}
      {/* ========================================================= */}

      {currentStep === 2 && (
        <div className="bg-surface-container-lowest dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-lg overflow-hidden">
          <div className="p-6 border-b border-outline-variant dark:border-[#2A345E] bg-surface-container-low dark:bg-[#1A1C24]">
            <h3 className="font-headline-sm text-on-surface dark:text-molten-text">
              Bot Configuration
            </h3>

            <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mt-1">
              Choose the AI bot that will handle calls for this event.
            </p>
          </div>

          <div className="p-6 space-y-6">
            {/* Primary Bot */}
            <div>
              <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">
                Primary Bot
              </label>

              <select
                value={formData.primary_bot_id}
                onChange={(e) => handleChange("primary_bot_id", e.target.value)}
                className="w-full p-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary"
              >
                <option value="">Select a bot</option>

                {botConfigs
                  .filter((bot) => bot.client_id === formData.client_id)
                  .map((bot) => (
                    <option key={bot.id} value={bot.id}>
                      {bot.name}
                    </option>
                  ))}
              </select>

              <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mt-1">
                This bot will be used as the primary AI agent for the event.
              </p>
            </div>

            {/* Outcome Configuration */}
            <div className="border border-outline-variant dark:border-[#2A345E] rounded-lg p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h4 className="font-medium text-on-surface dark:text-molten-text">
                    Configure Bot with Outcomes
                  </h4>

                  <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mt-1">
                    Configure how the bot handles different lead outcomes and
                    conversation scenarios.
                  </p>
                </div>

                <button
                  type="button"
                  disabled={!formData.primary_bot_id || isLoadingOutcomes}
                  onClick={handleConfigureOutcomes}
                  className="shrink-0 px-4 py-2 rounded-lg border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text hover:bg-surface-container dark:hover:bg-[#1A1C24] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isLoadingOutcomes ? "Loading..." : "Configure"}
                  {!isLoadingOutcomes && (
                    <span className="material-symbols-outlined align-middle ml-1 text-[18px]">
                      arrow_forward
                    </span>
                  )}
                </button>
              </div>
            </div>
            {showOutcomeConfig && (
              <div className="border border-outline-variant dark:border-[#2A345E] rounded-lg p-5">
                <div className="mb-4">
                  <h4 className="font-medium text-on-surface dark:text-molten-text">
                    Outcome → Bot Mapping
                  </h4>

                  <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mt-1">
                    Select which bot should handle each outcome after the
                    primary bot finishes the conversation.
                  </p>
                </div>

                {outcomes.length === 0 ? (
                  <div className="p-4 rounded-lg border border-dashed border-outline-variant dark:border-[#2A345E] text-sm text-on-surface-variant dark:text-molten-text-muted">
                    No outcomes are configured for this bot.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {outcomes.map((outcome) => (
                      <div
                        key={outcome}
                        className="grid grid-cols-1 md:grid-cols-2 gap-4 items-center p-3 rounded-lg bg-surface-container-low dark:bg-[#1A1C24]"
                      >
                        <div>
                          <p className="text-sm font-medium text-on-surface dark:text-molten-text">
                            {outcome}
                          </p>

                          <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mt-1">
                            Bot to use for this outcome
                          </p>
                        </div>

                        <select
                          value={outcomeBotMappings[outcome] || ""}
                          onChange={(e) => {
                            setOutcomeBotMappings((prev) => ({
                              ...prev,
                              [outcome]: e.target.value,
                            }));
                          }}
                          className="w-full p-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary"
                        >
                          <option value="">No follow-up bot</option>

                          {botConfigs
                            .filter(
                              (bot) => bot.client_id === formData.client_id,
                            )
                            .map((bot) => (
                              <option key={bot.id} value={bot.id}>
                                {bot.name}
                              </option>
                            ))}
                        </select>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* STEP 3 - SCHEDULE & ATTEMPTS */}
      {/* ========================================================= */}

      {currentStep === 3 && (
        <div className="bg-surface-container-lowest dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-lg overflow-hidden">
          <div className="p-6 border-b border-outline-variant dark:border-[#2A345E] bg-surface-container-low dark:bg-[#1A1C24]">
            <h3 className="font-headline-sm text-on-surface dark:text-molten-text">
              Schedule & Attempts
            </h3>

            <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mt-1">
              Configure when calls should be triggered and how retry attempts
              should be scheduled.
            </p>
          </div>

          <div className="p-6">
            {/* Initial Call Delay */}
            <div>
              <label className="block text-sm font-medium text-on-surface dark:text-molten-text mb-1">
                Initial Call Delay
              </label>

              <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mb-3">
                After a lead is added to this event, wait this amount of time
                before starting the first call.
              </p>

              <div className="flex items-center gap-3">
                <input
                  type="number"
                  min="0"
                  value={formData.initial_call_delay_minutes}
                  onChange={(e) =>
                    handleChange(
                      "initial_call_delay_minutes",
                      Number(e.target.value),
                    )
                  }
                  className="w-32 px-3 py-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary"
                />

                <span className="text-sm text-on-surface-variant dark:text-molten-text-muted">
                  minutes
                </span>
              </div>
            </div>

            {/* Attempts */}
            <div className="mt-8 pt-8 border-t border-outline-variant dark:border-[#2A345E]">
              <label className="block text-sm font-medium text-on-surface dark:text-molten-text mb-1">
                Maximum Attempts
              </label>

              <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mb-3">
                Maximum number of times the system can attempt to call a lead.
              </p>

              <select
                value={formData.max_attempts}
                onChange={(e) =>
                  handleChange("max_attempts", Number(e.target.value))
                }
                className="w-32 px-3 py-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary"
              >
                <option value={1}>1 attempt</option>
                <option value={2}>2 attempts</option>
                <option value={3}>3 attempts</option>
                <option value={4}>4 attempts</option>
                <option value={5}>5 attempts</option>
              </select>
            </div>

            {/* Retry Delay */}
            <div className="mt-8 pt-8 border-t border-outline-variant dark:border-[#2A345E]">
              <label className="block text-sm font-medium text-on-surface dark:text-molten-text mb-1">
                Retry Delay
              </label>

              <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mb-3">
                Wait this amount of time before scheduling the next attempt
                after a retryable call outcome.
              </p>

              <div className="flex items-center gap-3">
                <input
                  type="number"
                  min="1"
                  value={formData.retry_delay_minutes}
                  onChange={(e) =>
                    handleChange("retry_delay_minutes", Number(e.target.value))
                  }
                  className="w-32 px-3 py-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary"
                />

                <span className="text-sm text-on-surface-variant dark:text-molten-text-muted">
                  minutes
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* STEP 4 - REVIEW */}
      {/* ========================================================= */}

      {currentStep === 4 && (
        <div className="bg-surface-container-lowest dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-lg overflow-hidden">
          <div className="p-6 border-b border-outline-variant dark:border-[#2A345E] bg-surface-container-low dark:bg-[#1A1C24]">
            <h3 className="font-headline-sm text-on-surface dark:text-molten-text">
              Review Event
            </h3>

            <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mt-1">
              Review your event configuration before creating the event.
            </p>
          </div>

          <div className="p-6 space-y-6">
            {/* Event Details */}
            <div>
              <h4 className="text-sm font-semibold text-on-surface dark:text-molten-text mb-3">
                Event Details
              </h4>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-on-surface-variant dark:text-molten-text-muted">
                    Event Name
                  </p>

                  <p className="mt-1 text-sm text-on-surface dark:text-molten-text">
                    {formData.name || "—"}
                  </p>
                </div>

                <div>
                  <p className="text-xs text-on-surface-variant dark:text-molten-text-muted">
                    Client
                  </p>

                  <p className="mt-1 text-sm text-on-surface dark:text-molten-text">
                    {clients.find((client) => client.id === formData.client_id)
                      ?.name || "—"}
                  </p>
                </div>

                <div className="md:col-span-2">
                  <p className="text-xs text-on-surface-variant dark:text-molten-text-muted">
                    Description
                  </p>

                  <p className="mt-1 text-sm text-on-surface dark:text-molten-text">
                    {formData.description || "—"}
                  </p>
                </div>

                <div>
                  <p className="text-xs text-on-surface-variant dark:text-molten-text-muted">
                    Lead Handling
                  </p>

                  <p className="mt-1 text-sm text-on-surface dark:text-molten-text">
                    {formData.lead_handling === "follow_up"
                      ? "Follow Up"
                      : formData.lead_handling === "handover"
                        ? "Handover"
                        : "—"}
                  </p>
                </div>
              </div>
            </div>

            {/* Lead Source */}
            <div className="pt-6 border-t border-outline-variant dark:border-[#2A345E]">
              <h4 className="text-sm font-semibold text-on-surface dark:text-molten-text mb-3">
                Lead Source
              </h4>

              <p className="text-sm text-on-surface dark:text-molten-text">
                {formData.source_types.length
                  ? formData.source_types.join(", ")
                  : "—"}
              </p>
            </div>

            {/* Bot Configuration */}
            <div className="pt-6 border-t border-outline-variant dark:border-[#2A345E]">
              <h4 className="text-sm font-semibold text-on-surface dark:text-molten-text mb-3">
                Bot Configuration
              </h4>

              <p className="text-sm text-on-surface dark:text-molten-text">
                {botConfigs.find((bot) => bot.id === formData.primary_bot_id)
                  ?.name || "—"}
              </p>
            </div>

            {/* Schedule & Attempts */}
            <div className="pt-6 border-t border-outline-variant dark:border-[#2A345E]">
              <h4 className="text-sm font-semibold text-on-surface dark:text-molten-text mb-3">
                Schedule & Attempts
              </h4>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <p className="text-xs text-on-surface-variant dark:text-molten-text-muted">
                    Initial Call Delay
                  </p>

                  <p className="mt-1 text-sm text-on-surface dark:text-molten-text">
                    {formData.initial_call_delay_minutes} minutes
                  </p>
                </div>

                <div>
                  <p className="text-xs text-on-surface-variant dark:text-molten-text-muted">
                    Maximum Attempts
                  </p>

                  <p className="mt-1 text-sm text-on-surface dark:text-molten-text">
                    {formData.max_attempts}
                  </p>
                </div>

                <div>
                  <p className="text-xs text-on-surface-variant dark:text-molten-text-muted">
                    Retry Delay
                  </p>

                  <p className="mt-1 text-sm text-on-surface dark:text-molten-text">
                    {formData.retry_delay_minutes} minutes
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* FOOTER */}
      {/* ========================================================= */}

      <div className="px-6 py-4 border-t border-outline-variant dark:border-[#2A345E] flex justify-end gap-2">
        <button
          type="button"
          disabled={isCreating}
          onClick={() => navigate("/admin/events")}
          className="px-4 py-2 rounded-lg text-on-surface-variant dark:text-molten-text border border-outline-variant dark:border-[#2A345E] hover:bg-surface-container dark:hover:bg-[#2A345E]/50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Cancel
        </button>

        <button
          type="button"
          disabled={
            isCreating ||
            (currentStep === 0 &&
              (!formData.name ||
                !formData.client_id ||
                !formData.lead_handling)) ||
            (currentStep === 1 && !formData.source_types.length) ||
            (currentStep === 2 && !formData.primary_bot_id)
          }
          onClick={currentStep === 4 ? handleSaveEvent : handleContinue}
          className="px-4 py-2 bg-primary dark:bg-molten-primary text-on-primary rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isCreating ? (
            <>
              <span className="material-symbols-outlined align-middle mr-1 text-[18px] animate-spin">
                progress_activity
              </span>
              {isEditMode ? "Saving..." : "Creating..."}
            </>
          ) : currentStep === 4 ? (
            isEditMode ? (
              "Save Changes"
            ) : (
              "Create Event"
            )
          ) : (
            "Continue"
          )}
        </button>
      </div>
    </div>
  );
}
