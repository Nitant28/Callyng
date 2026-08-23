import React, { useState } from 'react';
import {
  CASCADE_KINDS,
  ROLE_LABELS,
  getProviderSpec,
  getModelSpec,
  getLegacyState,
  hasVoiceField,
  isDeepgramAuraModel,
  resetRoleOnProviderChange,
  resetRoleOnModelChange,
  getRoleKeys,
} from '../lib/cascadeCatalog';

const inputClass =
  'w-full bg-surface-container-lowest dark:bg-[#1A1A24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-sm text-on-surface dark:text-molten-text';

function SettingField({ field, value, onChange }) {
  const id = `cascade-field-${field.key}`;

  if (field.type === 'boolean') {
    return (
      <label className="flex items-center gap-2 cursor-pointer text-sm text-on-surface dark:text-molten-text">
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
          className="rounded border-outline-variant"
        />
        {field.label}
      </label>
    );
  }

  if (field.type === 'select') {
    return (
      <div>
        <label htmlFor={id} className="block text-sm mb-1 text-on-surface dark:text-molten-text">
          {field.label}
        </label>
        <select
          id={id}
          className={inputClass}
          value={value ?? ''}
          onChange={(e) => onChange(e.target.value)}
        >
          {!field.required && <option value="">—</option>}
          {(field.options || []).map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </div>
    );
  }

  if (field.type === 'number') {
    return (
      <div>
        <label htmlFor={id} className="block text-sm mb-1 text-on-surface dark:text-molten-text">
          {field.label}
        </label>
        <input
          id={id}
          type="number"
          className={inputClass}
          value={value ?? ''}
          min={field.min}
          max={field.max}
          step={field.step ?? 'any'}
          onChange={(e) => {
            const raw = e.target.value;
            onChange(raw === '' ? undefined : parseFloat(raw));
          }}
        />
      </div>
    );
  }

  return (
    <div>
      <label htmlFor={id} className="block text-sm mb-1 text-on-surface dark:text-molten-text">
        {field.label}
      </label>
      <input
        id={id}
        type="text"
        className={inputClass}
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

function RecommendedVoices({ voices, onSelect }) {
  if (!voices?.length) return null;
  return (
    <div className="mb-3">
      <div className="text-xs font-semibold text-on-surface-variant dark:text-molten-text-muted mb-2">
        Recommended voices
      </div>
      <div className="flex flex-wrap gap-2">
        {voices.map((v) => (
          <button
            key={v.id}
            type="button"
            className="cascade-voice-chip"
            title={`${v.language} · ${v.gender}`}
            onClick={() => onSelect(v.id)}
          >
            {v.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function CascadeRoleColumn({ kind, catalog, providerKey, modelId, settings, voice, onUpdate }) {
  const [legacyDismissed, setLegacyDismissed] = useState(false);
  const roleCatalog = catalog?.[kind] || {};
  const providerSpec = getProviderSpec(catalog, kind, providerKey);
  const modelSpec = providerSpec ? getModelSpec(providerSpec, modelId) : null;
  const { providerUnknown, modelUnknown } = getLegacyState(catalog, kind, providerKey, modelId);
  const showLegacy = !legacyDismissed && (providerUnknown || modelUnknown);
  const deepgramAura = isDeepgramAuraModel(providerKey, modelSpec);
  const voiceInSettings = hasVoiceField(modelSpec);

  const handleProviderChange = (newProvider) => {
    const newProviderSpec = getProviderSpec(catalog, kind, newProvider);
    const { model, settings: newSettings } = resetRoleOnProviderChange(newProviderSpec);
    const patch = { provider: newProvider, model, settings: newSettings };
    if (kind === 'tts') {
      const newModelSpec = getModelSpec(newProviderSpec, model);
      patch.voice = isDeepgramAuraModel(newProvider, newModelSpec)
        ? ''
        : (newSettings.voice ?? '');
    }
    onUpdate(patch);
  };

  const handleModelChange = (newModel) => {
    const newModelSpec = getModelSpec(providerSpec, newModel);
    const newSettings = resetRoleOnModelChange(newModelSpec, settings);
    const patch = { model: newModel, settings: newSettings };
    if (kind === 'tts') {
      if (isDeepgramAuraModel(providerKey, newModelSpec)) {
        patch.voice = '';
      } else if (newSettings.voice !== undefined) {
        patch.voice = newSettings.voice;
      } else if (voiceInSettings) {
        patch.voice = voice || '';
      }
    }
    onUpdate(patch);
  };

  const handleSettingChange = (key, value) => {
    const next = { ...settings, [key]: value };
    const patch = { settings: next };
    if (kind === 'tts' && key === 'voice') {
      patch.voice = value ?? '';
    }
    onUpdate(patch);
  };

  const handleVoiceColumnChange = (newVoice) => {
    const patch = { voice: newVoice };
    if (voiceInSettings) {
      patch.settings = { ...settings, voice: newVoice };
    }
    onUpdate(patch);
  };

  const handleRecommendedVoice = (voiceId) => {
    const patch = { voice: voiceId };
    if (voiceInSettings) {
      patch.settings = { ...settings, voice: voiceId };
    } else {
      patch.settings = { ...settings, voice: voiceId };
    }
    onUpdate(patch);
  };

  return (
    <div className="cascade-role-column">
      <h4 className="font-bold text-on-surface dark:text-molten-text mb-3 text-sm uppercase tracking-wide">
        {ROLE_LABELS[kind] || kind}
      </h4>

      {showLegacy && (
        <div className="cascade-legacy-banner mb-3 flex justify-between gap-2">
          <span>
            Stored {providerUnknown ? 'provider' : 'model'}{' '}
            <code className="text-xs">{providerUnknown ? providerKey : modelId}</code> is not in the
            current catalog — pick a new value before saving.
          </span>
          <button
            type="button"
            className="shrink-0 text-xs underline opacity-80"
            onClick={() => setLegacyDismissed(true)}
          >
            Dismiss
          </button>
        </div>
      )}

      <div className="space-y-3">
        <div>
          <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Provider</label>
          <select
            className={inputClass}
            value={providerKey || ''}
            onChange={(e) => handleProviderChange(e.target.value)}
          >
            {providerUnknown && providerKey && (
              <option value={providerKey} disabled>
                {providerKey} (not in catalog)
              </option>
            )}
            {Object.entries(roleCatalog).map(([key, spec]) => (
              <option key={key} value={key}>
                {spec.label}
              </option>
            ))}
          </select>
          {providerSpec && !providerSpec.key_configured && (
            <p className="cascade-key-warning mt-2">
              API key not configured on server — calls will fail
            </p>
          )}
        </div>

        <div>
          <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Model</label>
          <select
            className={inputClass}
            value={modelId || ''}
            onChange={(e) => handleModelChange(e.target.value)}
            disabled={!providerSpec && !providerUnknown}
          >
            {modelUnknown && modelId && (
              <option value={modelId} disabled>
                {modelId} (not in catalog)
              </option>
            )}
            {providerSpec &&
              Object.entries(providerSpec.models || {}).map(([mid, mspec]) => (
                <option key={mid} value={mid}>
                  {mspec.label}
                </option>
              ))}
          </select>
        </div>

        {kind === 'tts' && modelSpec?.recommended_voices?.length > 0 && (
          <>
            <RecommendedVoices
              voices={modelSpec.recommended_voices}
              onSelect={handleRecommendedVoice}
            />
            {providerKey === 'elevenlabs' && (
              <p className="text-xs text-on-surface-variant dark:text-molten-text-muted -mt-1 mb-2">
                Platform default voices may expire — prefer your account Voice Library for production.
              </p>
            )}
          </>
        )}

        {kind === 'tts' && !deepgramAura && !voiceInSettings && (
          <div>
            <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Voice ID</label>
            <input
              type="text"
              className={inputClass}
              value={voice || ''}
              onChange={(e) => handleVoiceColumnChange(e.target.value)}
              placeholder="Provider voice / speaker ID"
            />
          </div>
        )}

        {deepgramAura && (
          <p className="text-xs text-on-surface-variant dark:text-molten-text-muted">
            Voice is determined by the selected Aura-2 model.
          </p>
        )}

        {modelSpec?.fields?.length > 0 && (
          <div className="space-y-3 pt-2 border-t border-outline-variant/50 dark:border-[#2A345E]/50">
            <div className="text-xs font-semibold text-on-surface-variant dark:text-molten-text-muted">
              Settings
            </div>
            {modelSpec.fields.map((field) => (
              <SettingField
                key={field.key}
                field={field}
                value={settings?.[field.key]}
                onChange={(val) => handleSettingChange(field.key, val)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function CascadeModelsPanel({ catalog, editingConfig, onRoleUpdate }) {
  if (!catalog) {
    return (
      <div className="text-sm text-on-surface-variant dark:text-molten-text-muted py-8 text-center">
        Loading provider catalog…
      </div>
    );
  }

  return (
    <div>
      <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mb-4 leading-relaxed">
        STT, LLM, and TTS providers are loaded from the server catalog. Changing provider or model
        resets settings to defaults and removes fields that no longer apply.
      </p>
      <div className="cascade-models-grid">
        {CASCADE_KINDS.map((kind) => {
          const keys = getRoleKeys(kind);
          return (
            <CascadeRoleColumn
              key={kind}
              kind={kind}
              catalog={catalog}
              providerKey={editingConfig[keys.provider] || ''}
              modelId={editingConfig[keys.model] || ''}
              settings={editingConfig[keys.settings] || {}}
              voice={kind === 'tts' ? editingConfig.cascade_tts_voice || '' : undefined}
              onUpdate={(patch) => onRoleUpdate(kind, patch)}
            />
          );
        })}
      </div>
    </div>
  );
}
