import React, { useState } from 'react';

const GUIDE_MARKDOWN = `# Aakashvani STS Bot Scripting Guide

Writing an AI voice agent script is fundamentally different from building a traditional IVR tree. Gemini Live is fully conversational, meaning you must direct its **persona, pacing, and emotional intelligence** rather than hardcoding every single turn. 

This guide teaches you how to structure robust, natural-sounding agents using the bot_template.py architecture.

## 1. Core Principles
- **One Question, One Breath:** The AI should never ask two questions in the same turn. It confuses callers.
- **Listen First:** Instruct the bot to validate the caller's input before pushing to the next step.
- **Colloquialism Over Formality:** Use "Hinglish" or "Marathlish". Textbook Hindi/Marathi sounds robotic and breaks trust.
- **The Rule 0 Language Lock:** If a user explicitly says "Speak in English", the bot must lock that language and never auto-switch again.
- **Affective Responses:** Tell the bot how to react to emotions (e.g. "If caller sounds rushed: soften immediately, offer to keep it to one quick question or call back.")

## 2. Configuring Gemini Live Fields
- **GEMINI_MODEL**: Usually models/gemini-3.1-flash-live-preview
- **GEMINI_VOICE**: Aoede, Charon, or Sulafat.
- **GEMINI_TEMPERATURE**: Keep between 0.4 and 0.6.
- **GEMINI_LANGUAGE**: Must match primary language. hi-IN understands Marathi too.
- **GEMINI_VAD**: Start Sensitivity HIGH, End Sensitivity LOW.

## 3. The System Instruction Template
- **The Scene & Persona**: Define exactly who the bot is, where they are sitting, their mood.
- **Emotional Intelligence**: Map out how to react to user tones.
- **Call Flow**: Give explicit branching logic (Rule 1, Rule 2).
- **Language Rules**: Explicitly define code-switching behavior.
- **Call End Protocol**: Teach the bot when to hang up and invoke end_call tool.
`;

const ScriptingGuideModal = ({ isOpen, onClose }) => {
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(GUIDE_MARKDOWN);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 sm:p-6">
      <div className="bg-arctic-surface dark:bg-[#1A1A24] rounded-xl shadow-2xl w-full max-w-5xl max-h-[90vh] flex flex-col border border-outline-variant/50 dark:border-[#2A345E] overflow-hidden">
        {/* Header */}
        <div className="flex justify-between items-center px-6 py-4 border-b border-outline-variant dark:border-[#2A345E] bg-surface dark:bg-[#1C1810]">
          <h3 className="font-headline-md text-on-surface dark:text-molten-text flex items-center gap-2">
            <span className="material-symbols-outlined text-primary dark:text-molten-primary">menu_book</span>
            Aakashvani Scripting Guide
          </h3>
          <div className="flex items-center gap-3">
            <button 
              onClick={handleCopy}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-primary/10 text-primary dark:bg-molten-primary/10 dark:text-molten-primary rounded-lg text-sm font-medium hover:bg-primary/20 dark:hover:bg-molten-primary/20 transition-colors"
            >
              <span className="material-symbols-outlined text-[18px]">
                {copied ? 'check' : 'content_copy'}
              </span>
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

        {/* Content */}
        <div className="overflow-y-auto px-8 py-6 space-y-8 text-on-surface dark:text-molten-text">
          
          <section>
            <h4 className="text-xl font-bold mb-4 text-primary dark:text-molten-primary border-b border-outline-variant dark:border-[#2A345E] pb-2">
              1. The Anatomy of a Robust Script
            </h4>
            <p className="mb-4 text-on-surface-variant dark:text-molten-text-muted leading-relaxed">
              Writing an AI agent script is not like writing a traditional IVR tree. Gemini Live is fully conversational, meaning you must direct its <strong>persona, pacing, and emotional intelligence</strong> rather than hardcoding every single turn.
            </p>
            <div className="bg-surface-container-lowest dark:bg-[#1C1810] p-4 rounded-lg border border-outline-variant dark:border-[#2A345E]">
              <h5 className="font-bold mb-2">Core Principles:</h5>
              <ul className="list-disc pl-5 space-y-1 text-sm">
                <li><strong>One Question, One Breath:</strong> The AI should never ask two questions in the same turn.</li>
                <li><strong>Listen First:</strong> Instruct the bot to validate the caller's input before pushing to the next step.</li>
                <li><strong>Colloquialism Over Formality:</strong> Use "Hinglish" or "Marathlish". Textbook Hindi/Marathi sounds robotic and breaks trust.</li>
                <li><strong>The Rule 0 Language Lock:</strong> If a user explicitly says "Speak in English", the bot must lock that language and never auto-switch again.</li>
              </ul>
            </div>
          </section>

          <section>
            <h4 className="text-xl font-bold mb-4 text-primary dark:text-molten-primary border-b border-outline-variant dark:border-[#2A345E] pb-2">
              2. Configuring Gemini Live Fields
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h5 className="font-bold text-lg mb-2">Voice & Language</h5>
                <ul className="space-y-3 text-sm">
                  <li><strong className="text-primary dark:text-molten-primary">Language:</strong> Must match the primary language of the script (e.g., <code>hi-IN</code>, <code>en-IN</code>, <code>mr-IN</code>). A mismatch destroys transcription quality. Note: <code>hi-IN</code> is remarkably good at understanding Marathi too!</li>
                  <li><strong className="text-primary dark:text-molten-primary">Voice:</strong> <code>Aoede</code> (neutral female), <code>Charon</code> (warm male), <code>Sulafat</code> (warm female). Test these to see what fits your persona!</li>
                  <li><strong className="text-primary dark:text-molten-primary">Temperature:</strong> Keep between <strong>0.4 and 0.6</strong> for scripted conversational agents. Higher values make the bot go off-script; lower values make it sound robotic.</li>
                </ul>
              </div>
              <div>
                <h5 className="font-bold text-lg mb-2">Voice Activity Detection (VAD)</h5>
                <p className="text-sm mb-2 text-on-surface-variant dark:text-molten-text-muted">Critical for Indian languages where short affirmatives ("haan", "ji", "ho") are common.</p>
                <ul className="space-y-3 text-sm">
                  <li><strong className="text-primary dark:text-molten-primary">Start Sensitivity:</strong> Set to <code>HIGH</code>. This ensures the bot hears 150ms micro-bursts like "haan".</li>
                  <li><strong className="text-primary dark:text-molten-primary">End Sensitivity:</strong> Set to <code>LOW</code>. This forces the bot to wait a beat longer before cutting off slow speakers.</li>
                  <li><strong className="text-primary dark:text-molten-primary">Silence Duration:</strong> <code>400ms - 650ms</code>. Higher values prevent the bot from interrupting.</li>
                </ul>
              </div>
            </div>
          </section>

          <section>
            <h4 className="text-xl font-bold mb-4 text-primary dark:text-molten-primary border-b border-outline-variant dark:border-[#2A345E] pb-2">
              3. The System Instruction Template
            </h4>
            <p className="mb-4 text-sm leading-relaxed">
              This is the brain of your agent. You must structure it with clear sections:
            </p>
            <div className="space-y-4">
              <div className="bg-surface-container-lowest dark:bg-[#1C1810] p-4 rounded-lg border border-outline-variant dark:border-[#2A345E]">
                <h5 className="font-bold text-sm text-primary dark:text-molten-primary">THE SCENE & PERSONA</h5>
                <p className="text-sm mt-1">Define exactly who the bot is, where they are sitting, their mood, and their objective. <i>"You are Aryan, a relationship manager sitting in a calm Pune office. You are not a pushy salesperson..."</i></p>
              </div>
              <div className="bg-surface-container-lowest dark:bg-[#1C1810] p-4 rounded-lg border border-outline-variant dark:border-[#2A345E]">
                <h5 className="font-bold text-sm text-primary dark:text-molten-primary">EMOTIONAL INTELLIGENCE</h5>
                <p className="text-sm mt-1">Map out how to react to user tones. <i>"If caller sounds rushed: soften immediately, offer to keep it to one quick question or call back."</i></p>
              </div>
              <div className="bg-surface-container-lowest dark:bg-[#1C1810] p-4 rounded-lg border border-outline-variant dark:border-[#2A345E]">
                <h5 className="font-bold text-sm text-primary dark:text-molten-primary">CALL FLOW (Rule 1, Rule 2...)</h5>
                <p className="text-sm mt-1">Give explicit branching logic. For example: <i>"Rule 3: Ask if they are actively looking. If yes -&gt; go to Rule 4. If no -&gt; close gracefully as Not Interested."</i></p>
              </div>
              <div className="bg-surface-container-lowest dark:bg-[#1C1810] p-4 rounded-lg border border-outline-variant dark:border-[#2A345E]">
                <h5 className="font-bold text-sm text-primary dark:text-molten-primary">CALL END PROTOCOL</h5>
                <p className="text-sm mt-1">Teach the bot when to hang up. Tell it to say a goodbye phrase and immediately invoke the <code>end_call</code> tool.</p>
              </div>
            </div>
          </section>

          <section>
            <h4 className="text-xl font-bold mb-4 text-primary dark:text-molten-primary border-b border-outline-variant dark:border-[#2A345E] pb-2">
              4. Advanced Settings
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h5 className="font-bold text-lg mb-2">Bootstrap Messages (JSON)</h5>
                <p className="text-sm mb-2 text-on-surface-variant dark:text-molten-text-muted">Fires instantly when the call connects to eliminate latency.</p>
                <pre className="bg-black/50 p-3 rounded text-xs overflow-x-auto text-green-400 border border-outline-variant/30">
{`[
  {
    "role": "user",
    "content": "The call just connected. Execute Rule 1: say ONLY 'Hello... {lead_name} ji bol rahe hain?' in a warm voice. Stop completely."
  }
]`}
                </pre>
              </div>
              <div>
                <h5 className="font-bold text-lg mb-2">Goodbye Markers (JSON)</h5>
                <p className="text-sm mb-2 text-on-surface-variant dark:text-molten-text-muted">A safety net. If the bot forgets to invoke <code>end_call</code>, the server will auto-hangup if it hears any of these substrings.</p>
                <pre className="bg-black/50 p-3 rounded text-xs overflow-x-auto text-green-400 border border-outline-variant/30">
{`[
  "aapka din shubh ho",
  "din shubh ho",
  "zarurat note kar li",
  "have a great day"
]`}
                </pre>
              </div>
            </div>
            
            <div className="mt-6">
              <h5 className="font-bold text-lg mb-2">Extraction Schema (JSON)</h5>
              <p className="text-sm mb-2 text-on-surface-variant dark:text-molten-text-muted">Runs post-call on Groq to extract structured data from the transcript.</p>
              <pre className="bg-black/50 p-3 rounded text-xs overflow-x-auto text-green-400 border border-outline-variant/30">
{`{
  "mode": "fields",
  "fields": [
    {
      "key": "intent_status",
      "type": "enum",
      "values": ["Interested", "Not_Interested", "Busy", "Callback_Requested", "Wrong_Requirement"],
      "required": true
    }
  ],
  "extraction_rules": "Infer only what the transcript supports."
}`}
              </pre>
            </div>
          </section>

        </div>
      </div>
    </div>
  );
};

export default ScriptingGuideModal;
