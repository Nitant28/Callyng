/**
 * Lead-sheet column visibility.
 * Required columns are always shown; only optional IDs are persisted.
 */

const STORAGE_PREFIX = 'swarna:lead-sheet-columns';

export const REQUIRED_LEAD_SHEET_COLUMNS = [
  { id: 'name', label: 'Name', required: true },
  { id: 'phone', label: 'Phone', required: true },
  { id: 'status', label: 'Status', required: true },
  { id: 'outcome', label: 'Outcome', required: true },
  { id: 'turns', label: 'Turns', required: true },
  { id: 'attempts', label: 'Attempts', required: true },
  { id: 'actions', label: 'Actions', required: true },
];

export const OPTIONAL_SYSTEM_LEAD_SHEET_COLUMNS = [
  { id: 'follow_up', label: 'Follow-up', required: false },
  { id: 'whatsapp', label: 'WhatsApp', required: false },
  { id: 'email', label: 'Email', required: false },
  { id: 'last_follow_up', label: 'Last Follow-up', required: false },
];

export const DEFAULT_OPTIONAL_COLUMN_IDS = OPTIONAL_SYSTEM_LEAD_SHEET_COLUMNS.map((c) => c.id);

export function schemaColumnId(key) {
  return `schema:${key}`;
}

export function buildAvailableLeadSheetColumns(schemaFields = []) {
  const schemaCols = (schemaFields || []).map((field) => ({
    id: schemaColumnId(field.key),
    key: field.key,
    label: field.label || field.key,
    required: false,
    schema: true,
  }));
  return [...REQUIRED_LEAD_SHEET_COLUMNS, ...OPTIONAL_SYSTEM_LEAD_SHEET_COLUMNS, ...schemaCols];
}

export function defaultSelectedOptionalIds() {
  return [...DEFAULT_OPTIONAL_COLUMN_IDS];
}

export function storageKey(campaignId) {
  return `${STORAGE_PREFIX}:${campaignId || 'unknown'}`;
}

export function loadSelectedOptionalIds(campaignId, availableOptionalIds = []) {
  if (!campaignId) return defaultSelectedOptionalIds();
  try {
    const raw = localStorage.getItem(storageKey(campaignId));
    if (!raw) return defaultSelectedOptionalIds();
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return defaultSelectedOptionalIds();
    const allowed = new Set(availableOptionalIds);
    const cleaned = parsed.filter((id) => allowed.has(id) || !allowed.size);
    return cleaned;
  } catch {
    return defaultSelectedOptionalIds();
  }
}

export function saveSelectedOptionalIds(campaignId, ids) {
  if (!campaignId) return;
  try {
    localStorage.setItem(storageKey(campaignId), JSON.stringify(ids || []));
  } catch {
    /* ignore quota / private mode */
  }
}

export function resolveVisibleColumnIds(availableColumns, selectedOptionalIds) {
  const selected = new Set(selectedOptionalIds || []);
  return (availableColumns || [])
    .filter((col) => col.required || selected.has(col.id))
    .map((col) => col.id);
}

export function isColumnVisible(visibleIds, id) {
  return (visibleIds || []).includes(id);
}

export function getOptionalColumnIds(availableColumns) {
  return (availableColumns || []).filter((col) => !col.required).map((col) => col.id);
}
