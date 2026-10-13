import React, { useState } from 'react';

const GUIDE_MARKDOWN = `# ROLE
You generate paste-ready Aakashvani CMS fields for route=cascaded (STT→LLM→TTS on 8 kHz PSTN).
You are NOT writing a Python bot. You are NOT writing an STS/Gemini Live script.

The human message after this prompt is the campaign brief (product, language, persona, facts).
Use ONLY those facts in KNOWLEDGE BASE. Invent no prices, inventory, or company details.

# HARD RULES
1. Output exactly 8 sections with the headings below. Nothing before SECTION 1. Nothing after the checklist.
2. Each section body is copy-pasteable into the named CMS field. No markdown fences around SECTION 1 (plain text). JSON sections must be valid JSON only (no commentary inside the JSON).
3. Allowed live tools: ONLY \`end_call\`, \`push_lead_data\`, \`transfer_call\`. Never invent hangup, save_lead, transfer_to, dial, destination, phone.
4. \`transfer_call\` arguments: optional \`reason\` (string) ONLY. Forbidden keys: destination, number, to, phone, transfer_number.
5. \`end_call\` arguments: none (empty object / no args).
6. Never put \`Transferred\` in extraction \`intent_status\` or outcome_event_map. That outcome is set by the platform after transfer_call.
7. Always include the TOOLS block in SECTION 1 (gated by "only if listed in your tools"). Do not omit transfer protocol even if the brief does not mention transfer — operators enable it later in CMS.
8. Template variables allowed: {lead_name} {lead_phone} {lead_city} only.

# TOOL CONTRACT (must appear inside SECTION 1 as a heading "## TOOLS")

Copy this block into the system instruction. You may translate hold-lines and examples to the campaign language. Do not rename tools. Do not add tools. Do not change argument names.

## TOOLS
You may call a tool only if it is in your available tool list.

end_call — always available. No arguments.
  Speak the final goodbye first. Then call end_call exactly once.
  Never mid-call. Never before goodbye. Never twice.

push_lead_data — only if listed. Call exactly once on a NORMAL hangup (not after transfer).
  Then speak goodbye. Then end_call.
  Arguments (JSON):
  {
    "intent_status": "<Interested|Not_Interested|Busy|Callback_Requested|Wrong_Requirement|Unknown>",
    "bhk_preference": "<e.g. 2BHK> or \\"NULL\\"",
    "location_preference": "<area> or \\"NULL\\"",
    "callback_time": "<string or omit>",
    "language_used": "<Hindi|Marathi|English>"
  }
  Required: intent_status, bhk_preference, location_preference.
  Unknown collected fields MUST be the string NULL (not empty, not omit required keys).

transfer_call — only if listed. Cold-transfer to a human. Destination is NOT an argument.
  Optional: { "reason": "<short why>" }
  When the caller clearly asks for a human / executive / "transfer karo":
    1. Speak one hold line (do not say the destination number).
    2. Call transfer_call.
    3. Stop. Do not end_call. Do not push_lead_data after transfer.
  If transfer_call is NOT listed: offer a callback. Never pretend you transferred.

DECISION TABLE (use this, do not improvise):
| Situation | Speak | Then call |
|---|---|---|
| Caller wants a human AND transfer_call is listed | 1 hold sentence | transfer_call only |
| Normal end (done / not interested / busy after time taken) | — | push_lead_data (if listed), then goodbye, then end_call |
| transfer_call NOT listed but caller wants a human | offer callback, then goodbye | push_lead_data (if listed), then end_call |
| Ambiguous last turn / STT glitch | one clarifying question | no tool |

# OUTPUT — 8 SECTIONS

Use these headings exactly:

## SECTION 1 — system_instruction_template
(plain text)

Must contain, in this order:
AUDIO PROFILE; THE SCENE; DIRECTOR'S NOTES; AGENT PERSONA; LANGUAGE;
TOOLS (the contract above, translated hold-lines only);
CONVERSATIONAL STEPS (Step 1 = one Hindi/campaign-language question using {lead_name});
SPECIAL SITUATIONS (busy, not interested, human request, wrong requirement, trust, audio-once);
CALL ENDING (normal hangup order);
KNOWLEDGE BASE (brief facts only);
GUARDRAILS;
CALL METADATA (internal; do not read {lead_phone} / {lead_city} aloud).

## SECTION 2 — bootstrap_messages_json
JSON array only:
[{"role":"user","content":"The call has just connected. {lead_name} has answered. Execute Step 1: say ONLY the Step 1 opening sentence, addressing {lead_name} — then stop and wait. Do not say anything else."}]

## SECTION 3 — lead_schema
JSON object only. Default: {"fields":[]}. Add fields only if the brief needs extra CSV columns.

## SECTION 4 — extraction_schema
JSON object only. mode MUST be "both". Must include required enum field intent_status.
intent_status values MUST be a subset of:
Interested, Not_Interested, Busy, Callback_Requested, Wrong_Requirement, Unknown
NEVER include Transferred.
Include summary_prompt. Optional extra fields only if the brief needs them.

## SECTION 5 — outcome_event_map
JSON object only. Keys = intent_status values that should fire a webhook. Do not map Transferred.
Use {} if none.

## SECTION 6 — normalization_rules
JSON array only. Use [] unless the brief needs deterministic corrections.

## SECTION 7 — goodbye_markers
JSON array of short substrings (Devanagari AND romanized). Terminal goodbyes only. Do not include transfer hold-lines.

## SECTION 8 — cascade_live_tools
JSON array only. Paste into Advanced → Call actions → Live tools.
Unless the brief defines extra log-only tools, output EXACTLY this (do not rename keys):

[
  {
    "name": "push_lead_data",
    "description": "Call this before ending every call to save lead qualification data. Always call this regardless of outcome. Do not call after transfer_call.",
    "properties": {
      "intent_status": {
        "type": "string",
        "description": "Call outcome: Interested, Not_Interested, Busy, Callback_Requested, Wrong_Requirement, Unknown"
      },
      "bhk_preference": {
        "type": "string",
        "description": "BHK preference, or the string NULL if not collected"
      },
      "location_preference": {
        "type": "string",
        "description": "Preferred location, or the string NULL if not collected"
      },
      "callback_time": {
        "type": "string",
        "nullable": true,
        "description": "Requested callback time if busy; omit or null if none"
      },
      "language_used": {
        "type": "string",
        "description": "Language used in call: Hindi, Marathi, English"
      }
    },
    "required": ["intent_status", "bhk_preference", "location_preference"]
  }
]

Do NOT put end_call or transfer_call in this JSON. Those are registered by the platform, not this array.

# OPERATOR NOTE (do not output this as a CMS field)
After paste: turn Live tools ON. Turn Transfer calling ON only when an E.164 desk number exists.
Save fails if Live tools is on and this JSON is empty, or Transfer is on and the number is invalid.

# SELF-CHECK (print as a final bullet list, not a CMS field)
- [ ] 8 sections, exact headings
- [ ] SECTION 1 contains ## TOOLS with end_call, push_lead_data, transfer_call and the decision table
- [ ] No invented tool names or transfer destination args
- [ ] extraction intent_status has no Transferred
- [ ] SECTION 8 is valid JSON and only push_lead_data (unless brief explicitly added another named tool)
`;

const CascadeScriptingGuideModal = ({ isOpen, onClose }) => {
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState('tools');

  if (!isOpen) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(GUIDE_MARKDOWN);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const fieldSections = [
    {
      num: 1,
      title: 'System Instruction Template',
      field: 'system_instruction_template',
      tab: 'Prompts',
      type: 'Plain Text',
      icon: 'description',
      color: 'blue',
      required: true,
      description:
        'Master prompt for the cascade LLM (Groq/OpenAI/Google), not Gemini Live. Must document tool order: transfer_call vs push_lead_data + end_call.',
      structure: [
        'THE SCENE & DIRECTOR NOTES',
        'AGENT PERSONA',
        'LANGUAGE',
        'TOOLS — end_call, push_lead_data, transfer_call (availability + order)',
        'CONVERSATIONAL STEPS (opening → qualify → close)',
        'SPECIAL SITUATIONS including human/transfer request',
        'CALL ENDING — tool order',
        'KNOWLEDGE BASE + GUARDRAILS',
      ],
    },
    {
      num: 2,
      title: 'Bootstrap Messages',
      field: 'bootstrap_messages_json',
      tab: 'Prompts',
      type: 'JSON Array',
      icon: 'play_circle',
      color: 'green',
      required: true,
      description:
        'Keep aligned with Step 1. The live cascade bot currently kicks off with a hardcoded connect line; keep this field correct for exports.',
      example: `[
  {
    "role": "user",
    "content": "The call has just connected. {lead_name} has answered. Execute Step 1 only, then wait."
  }
]`,
    },
    {
      num: 3,
      title: 'Lead Schema',
      field: 'lead_schema',
      tab: 'Advanced',
      type: 'JSON Object',
      icon: 'person',
      color: 'purple',
      required: false,
      description: 'Extra CSV columns for uploads. Same as STS.',
      example: `{ "fields": [] }`,
    },
    {
      num: 4,
      title: 'Extraction Schema',
      field: 'extraction_schema',
      tab: 'Post-call',
      type: 'JSON Object',
      icon: 'analytics',
      color: 'red',
      required: true,
      description:
        'Post-call Groq extract from transcript. Do not put Transferred in intent_status — that outcome is set by the transfer tool.',
      example: `{
  "mode": "both",
  "summary_prompt": "Summarise this cascade call in 2-3 sentences.",
  "fields": [
    {
      "key": "intent_status",
      "type": "enum",
      "values": ["Interested", "Not_Interested", "Busy",
                 "Callback_Requested", "Wrong_Requirement", "Unknown"],
      "required": true
    }
  ]
}`,
    },
    {
      num: 5,
      title: 'Outcome Event Map',
      field: 'outcome_event_map',
      tab: 'Post-call',
      type: 'JSON Object',
      icon: 'webhook',
      color: 'amber',
      required: false,
      description: 'Webhook names for extraction intents. Never map Transferred.',
      example: `{ "Interested": "lead_qualified" }`,
    },
    {
      num: 6,
      title: 'Normalization Rules',
      field: 'normalization_rules',
      tab: 'Post-call',
      type: 'JSON Array',
      icon: 'auto_fix_high',
      color: 'purple',
      required: false,
      description: 'Deterministic fixes after extraction. Same as STS.',
      example: `[]`,
    },
    {
      num: 7,
      title: 'Goodbye Hangup Markers',
      field: 'goodbye_markers',
      tab: 'Advanced',
      type: 'JSON Array',
      icon: 'call_end',
      color: 'rose',
      required: true,
      description: 'Fallback hangup substrings if end_call is skipped. Not for transfer hold-lines.',
    },
    {
      num: 8,
      title: 'Live tools JSON',
      field: 'cascade_live_tools',
      tab: 'Advanced → Call actions',
      type: 'JSON Array',
      icon: 'construction',
      color: 'blue',
      required: true,
      description:
        'Registers extra LLM tools. Paste ONLY push_lead_data here. end_call and transfer_call are platform tools — do not add them to this array.',
      example: `[
  {
    "name": "push_lead_data",
    "description": "Call this before ending every call to save lead qualification data. Always call this regardless of outcome. Do not call after transfer_call.",
    "properties": {
      "intent_status": { "type": "string", "description": "Interested, Not_Interested, Busy, Callback_Requested, Wrong_Requirement, Unknown" },
      "bhk_preference": { "type": "string", "description": "BHK or NULL" },
      "location_preference": { "type": "string", "description": "Location or NULL" },
      "callback_time": { "type": "string", "nullable": true, "description": "Callback time if busy" },
      "language_used": { "type": "string", "description": "Hindi, Marathi, or English" }
    },
    "required": ["intent_status", "bhk_preference", "location_preference"]
  }
]`,
    },
  ];

  const colorMap = {
    blue: { bg: 'bg-blue-500/10', border: 'border-blue-500', text: 'text-blue-500' },
    green: { bg: 'bg-emerald-500/10', border: 'border-emerald-500', text: 'text-emerald-500' },
    purple: { bg: 'bg-purple-500/10', border: 'border-purple-500', text: 'text-purple-500' },
    red: { bg: 'bg-red-500/10', border: 'border-red-500', text: 'text-red-500' },
    amber: { bg: 'bg-amber-500/10', border: 'border-amber-500', text: 'text-amber-500' },
    rose: { bg: 'bg-rose-500/10', border: 'border-rose-500', text: 'text-rose-500' },
  };

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 sm:p-6">
      <div className="bg-arctic-surface dark:bg-[#1A1A24] rounded-xl shadow-2xl w-full max-w-6xl max-h-[90vh] flex flex-col border border-outline-variant/50 dark:border-[#2A345E] overflow-hidden">
        <div className="flex flex-col border-b border-outline-variant dark:border-[#2A345E] bg-surface dark:bg-[#1C1810]">
          <div className="flex justify-between items-center px-6 py-4">
            <h3 className="font-headline-md text-on-surface dark:text-molten-text flex items-center gap-2">
              <span className="material-symbols-outlined text-primary dark:text-molten-primary">call_split</span>
              Cascade Script Guide
              <span className="text-xs font-normal px-2 py-0.5 rounded-full bg-primary/10 text-primary dark:bg-molten-primary/10 dark:text-molten-primary">
                STT → LLM → TTS
              </span>
            </h3>
            <div className="flex items-center gap-3">
              <button
                onClick={handleCopy}
                title="Copy this prompt, then paste it into ChatGPT/Claude/Cursor together with the campaign brief"
                className="flex items-center gap-1.5 px-3 py-1.5 bg-primary/10 text-primary dark:bg-molten-primary/10 dark:text-molten-primary rounded-lg text-sm font-medium hover:bg-primary/20 dark:hover:bg-molten-primary/20 transition-colors"
              >
                <span className="material-symbols-outlined text-[18px]">{copied ? 'check' : 'content_copy'}</span>
                {copied ? 'Copied!' : 'Copy for AI'}
              </button>
              <button
                onClick={onClose}
                className="text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-molten-surface p-1 rounded transition-colors"
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
          </div>
          <div className="flex px-6 gap-6 text-sm font-medium overflow-x-auto">
            {[
              { key: 'tools', label: 'Tools & transfer', icon: 'construction' },
              { key: 'fields', label: 'CMS fields', icon: 'format_list_numbered' },
              { key: 'stack', label: 'Stack & toggles', icon: 'tune' },
              { key: 'rules', label: 'Outcomes', icon: 'rule' },
            ].map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`pb-3 px-1 border-b-2 transition-colors shrink-0 ${
                  activeTab === tab.key
                    ? 'border-primary text-primary dark:border-molten-primary dark:text-molten-primary'
                    : 'border-transparent text-on-surface-variant hover:text-on-surface dark:text-molten-text-muted dark:hover:text-molten-text'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[18px]">{tab.icon}</span>
                  {tab.label}
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6 text-on-surface dark:text-molten-text">
          {activeTab === 'tools' && (
            <div className="space-y-6">
              <div className="bg-primary/10 dark:bg-molten-primary/10 border-l-4 border-primary dark:border-molten-primary p-4 rounded-r-lg">
                <h4 className="text-lg font-bold mb-1">AI: use Copy for AI + the campaign brief</h4>
                <p className="text-sm text-on-surface-variant dark:text-molten-text-muted">
                  The copied prompt is a contract: 8 paste-ready sections, exact tool names, exact JSON args.
                  Paste it into the model first, then the product brief. Do not let the model invent extra tools.
                </p>
              </div>

              <div className="overflow-x-auto text-sm">
                <table className="w-full border-collapse text-left">
                  <thead>
                    <tr className="border-b border-outline-variant dark:border-[#2A345E]">
                      <th className="p-2">Tool</th>
                      <th className="p-2">How it gets registered</th>
                      <th className="p-2">Arguments</th>
                    </tr>
                  </thead>
                  <tbody className="text-on-surface-variant dark:text-molten-text-muted">
                    <tr className="border-b border-outline-variant/50 dark:border-[#2A345E]">
                      <td className="p-2 font-mono">end_call</td>
                      <td className="p-2">Always (platform)</td>
                      <td className="p-2">none</td>
                    </tr>
                    <tr className="border-b border-outline-variant/50 dark:border-[#2A345E]">
                      <td className="p-2 font-mono">push_lead_data</td>
                      <td className="p-2">Live tools ON + listed in cascade_live_tools JSON</td>
                      <td className="p-2">intent_status, bhk_preference, location_preference required; NULL if unknown</td>
                    </tr>
                    <tr>
                      <td className="p-2 font-mono">transfer_call</td>
                      <td className="p-2">Transfer calling ON + valid E.164</td>
                      <td className="p-2">optional reason only — never a phone number</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <section className="space-y-3">
                <h4 className="font-bold text-lg">Decision table (must be in the system instruction)</h4>
                <div className="bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg p-4 text-sm font-mono whitespace-pre-wrap">
{`Caller wants human + transfer_call listed
  → hold line → transfer_call({reason}) → STOP (no end_call, no push_lead_data)

Normal hangup
  → push_lead_data (if listed) → goodbye → end_call()

Wants human but transfer_call NOT listed
  → offer callback → push_lead_data (if listed) → goodbye → end_call()

Unclear last turn
  → one clarifying question → no tool`}
                </div>
              </section>

              <section className="space-y-3">
                <h4 className="font-bold text-lg">Paste into Live tools JSON</h4>
                <p className="text-sm text-on-surface-variant dark:text-molten-text-muted">
                  Do not add end_call or transfer_call here. Names and required keys must match the prompt.
                </p>
                <pre className="text-xs overflow-x-auto bg-black/40 p-3 rounded">{`[
  {
    "name": "push_lead_data",
    "description": "Call this before ending every call to save lead qualification data. Always call this regardless of outcome. Do not call after transfer_call.",
    "properties": {
      "intent_status": { "type": "string", "description": "Interested, Not_Interested, Busy, Callback_Requested, Wrong_Requirement, Unknown" },
      "bhk_preference": { "type": "string", "description": "BHK or NULL" },
      "location_preference": { "type": "string", "description": "Location or NULL" },
      "callback_time": { "type": "string", "nullable": true, "description": "Callback time if busy" },
      "language_used": { "type": "string", "description": "Hindi, Marathi, or English" }
    },
    "required": ["intent_status", "bhk_preference", "location_preference"]
  }
]`}</pre>
              </section>
            </div>
          )}

          {activeTab === 'fields' && (
            <div className="space-y-4">
              {fieldSections.map((s) => {
                const c = colorMap[s.color] || colorMap.blue;
                return (
                  <div key={s.num} className={`rounded-lg border ${c.border} ${c.bg} p-4`}>
                    <div className="flex items-start gap-3">
                      <span className="material-symbols-outlined">{s.icon}</span>
                      <div className="min-w-0">
                        <h4 className={`font-bold ${c.text}`}>
                          {s.num}. {s.title}
                        </h4>
                        <p className="text-xs font-mono opacity-80 mb-2">
                          {s.field} · {s.tab} · {s.type}
                        </p>
                        <p className="text-sm mb-2">{s.description}</p>
                        {s.structure && (
                          <ul className="text-sm list-disc pl-5 space-y-1">
                            {s.structure.map((item) => (
                              <li key={item}>{item}</li>
                            ))}
                          </ul>
                        )}
                        {s.example && (
                          <pre className="mt-2 text-xs overflow-x-auto bg-black/40 p-3 rounded">{s.example}</pre>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {activeTab === 'stack' && (
            <div className="space-y-6 text-sm">
              <section>
                <h4 className="font-bold text-lg mb-2">Pipeline</h4>
                <p>
                  Telnyx 8 kHz audio → Silero VAD → STT → LLM (tool calls) → TTS → Telnyx.
                  This is not Gemini Live. Models-tab Gemini + VAD sliders do not apply.
                </p>
              </section>
              <section>
                <h4 className="font-bold text-lg mb-2">Models tab</h4>
                <p>
                  Pick STT / LLM / TTS from the catalog. Default Hindi outbound stack: Sarvam STT hi-IN,
                  Groq <code>openai/gpt-oss-120b</code>, Cartesia sonic-3.5 + Hindi narrator voice.
                  Inline warning if that vendor&apos;s API key is missing.
                </p>
              </section>
              <section>
                <h4 className="font-bold text-lg mb-2">Call actions (Advanced)</h4>
                <ul className="list-disc pl-5 space-y-1">
                  <li>Live tools + JSON — registers those function schemas (including push_lead_data).</li>
                  <li>Transfer calling + number — registers transfer_call. Number stored as E.164.</li>
                  <li>Save is blocked if a toggle is on but the number/JSON is invalid.</li>
                </ul>
              </section>
              <section>
                <h4 className="font-bold text-lg mb-2">Prompt must match registration</h4>
                <p>
                  Tool names in the system instruction must equal JSON <code>name</code> values.
                  The default cascaded template already includes the transfer protocol so you only need
                  to turn Transfer calling on and paste a number.
                </p>
              </section>
            </div>
          )}

          {activeTab === 'rules' && (
            <div className="space-y-4 text-sm">
              <p>
                Post-call extraction still fills <code>intent_status</code>. Drag those values into Terminal / Retry / Callback
                as on STS.
              </p>
              <p>
                <strong>Transferred</strong> is a system terminal outcome. It is not in the script&apos;s outcome buckets
                and cannot be turned off. Hangup will not schedule a callback after a successful transfer.
              </p>
              <p>
                After transfer, billed minutes ≈ bot pipeline duration only.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default CascadeScriptingGuideModal;
