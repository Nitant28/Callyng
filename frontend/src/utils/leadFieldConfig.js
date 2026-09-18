/** Per-campaign lead field helpers — mirrors campaigns/lead_field_config.py */

const RESERVED_KEYS = new Set(['name', 'phone', 'lead_name', 'lead_phone', 'lead_type']);

export const normalizeColumnKey = (key) =>
  String(key || '')
    .trim()
    .replace(/\s+/g, '_')
    .toLowerCase()
    .replace(/[^a-z0-9_]/g, '');

export function parseLeadMetadata(raw) {
  if (raw == null) return {};
  if (typeof raw === 'object' && !Array.isArray(raw)) return { ...raw };
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
    } catch {
      return {};
    }
  }
  return {};
}

export function metaValue(lead, key) {
  if (!lead || !key) return '';
  if (lead[key] != null && lead[key] !== '') return lead[key];
  const meta = parseLeadMetadata(lead.metadata);
  if (meta[key] != null && meta[key] !== '') return meta[key];
  const lower = String(key).toLowerCase();
  for (const [k, v] of Object.entries(meta)) {
    if (String(k).toLowerCase() === lower && v != null && v !== '') return v;
  }
  return '';
}

export function extractSchemaFields(schema) {
  if (!schema) return [];
  const rows = Array.isArray(schema.fields)
    ? schema.fields
    : Object.entries(schema)
        .filter(([, v]) => v && typeof v === 'object')
        .map(([key, value]) => ({ key, ...value }));

  const seen = new Set();
  const fields = [];
  rows.forEach((field) => {
    if (!field || typeof field !== 'object') return;
    const key = normalizeColumnKey(field.key || field.name || field.csv_column || '');
    if (!key || seen.has(key) || RESERVED_KEYS.has(key)) return;
    seen.add(key);
    fields.push({
      key,
      label: String(field.label || field.csv_column || field.name || key),
      required: Boolean(field.required),
      type: String(field.type || 'text') === 'string' ? 'text' : String(field.type || 'text'),
      placeholder: String(field.placeholder || field.description || ''),
      options: Array.isArray(field.options) ? field.options.map((o) => String(o ?? '')) : [],
    });
  });
  return fields;
}

export function resolveLeadFieldConfig(campaign, schemaFields = null) {
  const stored =
    campaign?.lead_field_config && typeof campaign.lead_field_config === 'object'
      ? campaign.lead_field_config
      : {};
  const fromSchema =
    schemaFields != null
      ? schemaFields
      : extractSchemaFields(campaign?.bot_config?.lead_schema);

  const seen = new Set();
  const fields = [];

  const push = (raw) => {
    if (!raw || typeof raw !== 'object') return;
    const key = normalizeColumnKey(raw.key || raw.name || '');
    if (!key || seen.has(key) || RESERVED_KEYS.has(key)) return;
    seen.add(key);
    fields.push({
      key,
      label: String(raw.label || raw.csv_column || raw.name || key),
      required: Boolean(raw.required),
      type: String(raw.type || 'text') === 'string' ? 'text' : String(raw.type || 'text'),
      placeholder: String(raw.placeholder || raw.description || ''),
      options: Array.isArray(raw.options) ? raw.options.map((o) => String(o ?? '')) : [],
    });
  };

  (fromSchema || []).forEach(push);
  (stored.fields || stored.custom_fields || []).forEach(push);

  return {
    enabled: stored.enabled !== false,
    require_name: stored.require_name !== false,
    require_phone: stored.require_phone !== false,
    fields,
    raw: stored,
  };
}

export function isFieldRequired(config, key) {
  if (!config || config.enabled === false) return key === 'phone';
  if (key === 'name') return config.require_name !== false;
  if (key === 'phone') return config.require_phone !== false;
  const field = (config.fields || []).find((f) => f.key === key);
  return Boolean(field?.required);
}

export function labelForField(config, key, fallback) {
  if (key === 'name') return 'Full Name';
  if (key === 'phone') return 'Phone Number';
  if (key === 'lead_type') return 'Lead Type';
  const field = (config?.fields || []).find((f) => f.key === key);
  return field?.label || fallback || key.replace(/_/g, ' ');
}

export function validateLeadForm(config, values, { isCreate = true } = {}) {
  const cfg = config || {};
  if (cfg.enabled === false) return [];

  const errors = [];
  const name = values?.name;
  const phone = values?.phone;
  const metadata = parseLeadMetadata(values?.metadata ?? values);

  if (cfg.require_name !== false && !String(name || '').trim()) {
    if (isCreate || name !== undefined) errors.push('Name is required');
  }
  if (cfg.require_phone !== false && !String(phone || '').trim()) {
    if (isCreate || phone !== undefined) errors.push('Phone is required');
  }

  (cfg.fields || []).forEach((field) => {
    if (!field?.required || !field.key) return;
    const val = metadata[field.key] ?? values?.[field.key];
    if (val == null || (typeof val === 'string' && !val.trim())) {
      errors.push(`${field.label || field.key} is required`);
    }
  });

  return errors;
}
