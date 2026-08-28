/** Pure helpers for cascade provider catalog (Phase 1b). */

export const CASCADE_KINDS = ['stt', 'llm', 'tts'];

export const ROLE_LABELS = {
  stt: 'Speech-to-Text',
  llm: 'Language Model',
  tts: 'Text-to-Speech',
};

export function getRoleCatalog(catalog, kind) {
  if (!catalog || typeof catalog !== 'object') return null;
  return catalog[kind] ?? null;
}

export function getProviderSpec(catalog, kind, providerKey) {
  const roleCatalog = getRoleCatalog(catalog, kind);
  if (!roleCatalog || !providerKey) return null;
  return roleCatalog[providerKey] ?? null;
}

export function getModelSpec(providerSpec, modelId) {
  if (!providerSpec?.models || !modelId) return null;
  return providerSpec.models[modelId] ?? null;
}

export function buildSettingsFromDefaults(modelSpec) {
  if (!modelSpec?.fields?.length) return {};
  const out = {};
  for (const field of modelSpec.fields) {
    if (field.default !== null && field.default !== undefined) {
      out[field.key] = field.default;
    } else if (field.required) {
      out[field.key] = field.type === 'boolean' ? false : '';
    }
  }
  return out;
}

export function pruneSettings(current, modelSpec) {
  const base = current && typeof current === 'object' ? { ...current } : {};
  if (!modelSpec?.fields?.length) {
    return {};
  }
  const allowed = new Set(modelSpec.fields.map((f) => f.key));
  const pruned = {};
  for (const key of Object.keys(base)) {
    if (allowed.has(key)) {
      pruned[key] = base[key];
    }
  }
  const defaults = buildSettingsFromDefaults(modelSpec);
  for (const [key, value] of Object.entries(defaults)) {
    if (!(key in pruned)) {
      pruned[key] = value;
    }
  }
  return pruned;
}

export function resetRoleOnProviderChange(providerSpec) {
  if (!providerSpec) {
    return { model: '', settings: {} };
  }
  const model = providerSpec.default_model || '';
  const modelSpec = getModelSpec(providerSpec, model);
  return {
    model,
    settings: buildSettingsFromDefaults(modelSpec),
  };
}

export function resetRoleOnModelChange(modelSpec, currentSettings) {
  return pruneSettings(currentSettings, modelSpec);
}

export function hasVoiceField(modelSpec) {
  return Boolean(modelSpec?.fields?.some((f) => f.key === 'voice'));
}

export function isDeepgramAuraModel(providerKey, modelSpec) {
  return providerKey === 'deepgram' && (!modelSpec?.fields || modelSpec.fields.length === 0);
}

export function getRoleKeys(kind) {
  return {
    provider: `cascade_${kind}_provider`,
    model: `cascade_${kind}_model`,
    settings: `cascade_${kind}_settings`,
  };
}

/** Returns { providerUnknown, modelUnknown } for legacy/stale configs. */
export function getLegacyState(catalog, kind, providerKey, modelId) {
  const providerSpec = getProviderSpec(catalog, kind, providerKey);
  if (!providerKey) {
    return { providerUnknown: false, modelUnknown: false };
  }
  if (!providerSpec) {
    return { providerUnknown: true, modelUnknown: true };
  }
  const modelSpec = getModelSpec(providerSpec, modelId);
  if (!modelId) {
    return { providerUnknown: false, modelUnknown: false };
  }
  return { providerUnknown: false, modelUnknown: !modelSpec };
}

export function isCascadeConfigValidForSave(catalog, editingConfig) {
  if (!catalog || editingConfig?.route !== 'cascaded') return true;
  for (const kind of CASCADE_KINDS) {
    const keys = getRoleKeys(kind);
    const provider = editingConfig[keys.provider] || '';
    const model = editingConfig[keys.model] || '';
    if (!provider && !model) continue;
    const { providerUnknown, modelUnknown } = getLegacyState(catalog, kind, provider, model);
    if (providerUnknown || modelUnknown) return false;
  }
  return true;
}

export function normalizeCascadeSettings(config) {
  const stt =
    config.cascade_stt_settings && typeof config.cascade_stt_settings === 'object'
      ? { ...config.cascade_stt_settings }
      : {};
  const llm =
    config.cascade_llm_settings && typeof config.cascade_llm_settings === 'object'
      ? { ...config.cascade_llm_settings }
      : {};
  const tts =
    config.cascade_tts_settings && typeof config.cascade_tts_settings === 'object'
      ? { ...config.cascade_tts_settings }
      : {};
  let voice = config.cascade_tts_voice || '';
  if (tts.voice && !voice) {
    voice = tts.voice;
  } else if (voice && !tts.voice) {
    tts.voice = voice;
  }
  return {
    cascade_stt_settings: stt,
    cascade_llm_settings: llm,
    cascade_tts_settings: tts,
    cascade_tts_voice: voice,
  };
}
