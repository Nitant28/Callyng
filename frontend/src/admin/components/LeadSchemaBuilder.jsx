import React, { useMemo } from 'react';

const FIELD_TYPES = [
  { value: 'text', label: 'Text' },
  { value: 'number', label: 'Number' },
  { value: 'dropdown', label: 'Dropdown' },
];

function slugifyKey(label) {
  return String(label || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

function normalizeType(type) {
  return type === 'string' ? 'text' : (type || 'text');
}

function parseSchema(raw) {
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw || 'null') : raw;
    if (!parsed || typeof parsed !== 'object') return { fields: [] };
    if (Array.isArray(parsed.fields)) {
      return {
        fields: parsed.fields.map((f) => ({
          key: f.key != null ? String(f.key) : slugifyKey(f.label || f.csv_column || f.name || ''),
          label: f.label != null ? String(f.label) : String(f.csv_column || f.name || f.key || ''),
          type: normalizeType(f.type),
          required: Boolean(f.required),
          placeholder: f.placeholder != null ? String(f.placeholder) : String(f.description || ''),
          csv_column: f.csv_column != null ? String(f.csv_column) : String(f.label || f.key || ''),
          options: Array.isArray(f.options) ? f.options.map((o) => String(o ?? '')) : [],
        })),
      };
    }
    // Legacy object map → fields array
    const fields = Object.entries(parsed)
      .filter(([, v]) => v && typeof v === 'object')
      .map(([key, v]) => ({
        key,
        label: v.label != null ? String(v.label) : String(v.csv_column || key),
        type: normalizeType(v.type),
        required: Boolean(v.required),
        placeholder: v.placeholder != null ? String(v.placeholder) : String(v.description || ''),
        csv_column: v.csv_column != null ? String(v.csv_column) : String(v.label || key),
        options: Array.isArray(v.options) ? v.options.map((o) => String(o ?? '')) : [],
      }));
    return { fields };
  } catch {
    return { fields: [] };
  }
}

function toSchemaJson(fields) {
  return JSON.stringify(
    {
      fields: fields.map((f) => {
        const key = (f.key && String(f.key).trim()) || slugifyKey(f.label) || 'field';
        const label = f.label != null && String(f.label) !== '' ? String(f.label) : key;
        const out = {
          key,
          label,
          type: normalizeType(f.type),
          required: Boolean(f.required),
          csv_column: (f.csv_column != null && String(f.csv_column) !== '')
            ? String(f.csv_column)
            : label,
        };
        if (f.placeholder != null && String(f.placeholder) !== '') {
          out.placeholder = String(f.placeholder);
        }
        if (normalizeType(f.type) === 'dropdown' && Array.isArray(f.options)) {
          out.options = f.options.map((o) => String(o ?? '').trim()).filter(Boolean);
        }
        return out;
      }),
    },
    null,
    2,
  );
}

/**
 * Keep draft field values editable (empty strings allowed).
 * Finalize key/label/csv only when serializing via toSchemaJson.
 */
function draftFieldsFromValue(value) {
  return parseSchema(value).fields;
}

/**
 * Visual Lead Schema builder. Writes JSON string into onChange (same shape as textarea).
 */
export default function LeadSchemaBuilder({ value, onChange }) {
  const fields = useMemo(() => draftFieldsFromValue(value), [value]);

  const commit = (nextFields) => {
    // Persist draft-friendly JSON: keep typed values as-is so inputs don't snap back.
    onChange(JSON.stringify(
      {
        fields: nextFields.map((f) => {
          const out = {
            key: f.key ?? '',
            label: f.label ?? '',
            type: normalizeType(f.type),
            required: Boolean(f.required),
            csv_column: f.csv_column ?? '',
            placeholder: f.placeholder ?? '',
          };
          if (normalizeType(f.type) === 'dropdown') {
            out.options = Array.isArray(f.options) ? f.options : [];
          }
          return out;
        }),
      },
      null,
      2,
    ));
  };

  const updateField = (index, patch) => {
    const next = fields.map((f, i) => {
      if (i !== index) return f;
      const merged = { ...f, ...patch };

      if (Object.prototype.hasOwnProperty.call(patch, 'label')) {
        const prevAutoKey = slugifyKey(f.label);
        const nextAutoKey = slugifyKey(patch.label);
        // Only auto-sync key when it still matched the previous auto slug (or was empty)
        if (!f.key || f.key === prevAutoKey) {
          merged.key = nextAutoKey;
        }
        // Only auto-sync csv_column when it still mirrored label/key
        if (!f.csv_column || f.csv_column === f.label || f.csv_column === f.key) {
          merged.csv_column = patch.label;
        }
      }

      if (Object.prototype.hasOwnProperty.call(patch, 'key')) {
        merged.key = slugifyKey(patch.key);
      }

      return merged;
    });
    commit(next);
  };

  const addField = () => {
    commit([
      ...fields,
      {
        key: '',
        label: '',
        type: 'text',
        required: false,
        placeholder: '',
        csv_column: '',
        options: [],
      },
    ]);
  };

  const removeField = (index) => {
    commit(fields.filter((_, i) => i !== index));
  };

  const moveField = (index, dir) => {
    const j = index + dir;
    if (j < 0 || j >= fields.length) return;
    const next = [...fields];
    [next[index], next[j]] = [next[j], next[index]];
    commit(next);
  };

  // Pretty JSON for the debug panel — finalized shape (as saved)
  const finalizedPreview = useMemo(() => toSchemaJson(fields), [fields]);

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <label className="block text-sm mb-1 text-on-surface dark:text-molten-text font-semibold">
            Lead Schema
          </label>
          <p className="text-xs text-on-surface-variant dark:text-molten-text-muted">
            Defines the Add Lead form, Excel template, import validation, and export columns for every campaign using this script.
          </p>
        </div>
        <button
          type="button"
          onClick={addField}
          className="shrink-0 px-3 py-2 rounded-lg bg-primary/15 dark:bg-molten-primary/20 text-primary dark:text-molten-primary text-sm font-semibold flex items-center gap-1 hover:opacity-90"
        >
          <span className="material-symbols-outlined text-[18px]">add</span>
          Add Field
        </button>
      </div>

      {fields.length === 0 ? (
        <div className="border border-dashed border-outline-variant dark:border-[#2A345E] rounded-lg p-6 text-center text-sm text-on-surface-variant dark:text-molten-text-muted">
          No custom lead fields yet. Name, Phone, and Lead Type are always available. Click Add Field for City, Budget, etc.
        </div>
      ) : (
        <div className="space-y-3">
          {fields.map((field, index) => (
            <div
              key={`lead-field-${index}`}
              className="rounded-lg border border-outline-variant dark:border-[#2A345E] bg-surface-container-lowest dark:bg-[#1A1A24] p-4 space-y-3"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-bold uppercase tracking-wide text-on-surface-variant dark:text-molten-text-muted">
                  Field {index + 1}
                </span>
                <div className="flex items-center gap-1">
                  <button type="button" className="p-1 rounded hover:bg-surface-container dark:hover:bg-[#2A345E]/40" onClick={() => moveField(index, -1)} title="Move up" disabled={index === 0}>
                    <span className="material-symbols-outlined text-[18px]">arrow_upward</span>
                  </button>
                  <button type="button" className="p-1 rounded hover:bg-surface-container dark:hover:bg-[#2A345E]/40" onClick={() => moveField(index, 1)} title="Move down" disabled={index === fields.length - 1}>
                    <span className="material-symbols-outlined text-[18px]">arrow_downward</span>
                  </button>
                  <button type="button" className="p-1 rounded text-error dark:text-molten-error hover:bg-error/10" onClick={() => removeField(index)} title="Remove field">
                    <span className="material-symbols-outlined text-[18px]">delete</span>
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs mb-1 text-on-surface dark:text-molten-text">Label</label>
                  <input
                    type="text"
                    className="w-full px-3 py-2 rounded-lg bg-surface dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] text-sm text-on-surface dark:text-molten-text"
                    value={field.label ?? ''}
                    onChange={(e) => updateField(index, { label: e.target.value })}
                    placeholder="e.g. City"
                  />
                </div>
                <div>
                  <label className="block text-xs mb-1 text-on-surface dark:text-molten-text">Key (internal)</label>
                  <input
                    type="text"
                    className="w-full px-3 py-2 rounded-lg bg-surface dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] text-sm text-on-surface dark:text-molten-text font-mono"
                    value={field.key ?? ''}
                    onChange={(e) => updateField(index, { key: e.target.value })}
                    placeholder="city"
                  />
                </div>
                <div>
                  <label className="block text-xs mb-1 text-on-surface dark:text-molten-text">Type</label>
                  <select
                    className="w-full px-3 py-2 rounded-lg bg-surface dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] text-sm text-on-surface dark:text-molten-text"
                    value={normalizeType(field.type)}
                    onChange={(e) => updateField(index, { type: e.target.value })}
                  >
                    {FIELD_TYPES.map((t) => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs mb-1 text-on-surface dark:text-molten-text">Excel column name</label>
                  <input
                    type="text"
                    className="w-full px-3 py-2 rounded-lg bg-surface dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] text-sm text-on-surface dark:text-molten-text"
                    value={field.csv_column ?? ''}
                    onChange={(e) => updateField(index, { csv_column: e.target.value })}
                    placeholder="City"
                  />
                </div>
                <div className="md:col-span-2">
                  <label className="block text-xs mb-1 text-on-surface dark:text-molten-text">Placeholder</label>
                  <input
                    type="text"
                    className="w-full px-3 py-2 rounded-lg bg-surface dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] text-sm text-on-surface dark:text-molten-text"
                    value={field.placeholder ?? ''}
                    onChange={(e) => updateField(index, { placeholder: e.target.value })}
                    placeholder="Enter City"
                  />
                </div>
              </div>

              {normalizeType(field.type) === 'dropdown' && (
                <div>
                  <label className="block text-xs mb-1 text-on-surface dark:text-molten-text">Options (one per line)</label>
                  <textarea
                    rows={3}
                    className="w-full px-3 py-2 rounded-lg bg-surface dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] text-sm text-on-surface dark:text-molten-text"
                    value={(field.options || []).join('\n')}
                    onChange={(e) =>
                      updateField(index, {
                        // Keep empty lines while typing; trim/filter happens on save preview
                        options: e.target.value.split('\n'),
                      })
                    }
                    placeholder={'Doctor\nEngineer\nBusiness'}
                  />
                </div>
              )}

              <label className="inline-flex items-center gap-2 text-sm text-on-surface dark:text-molten-text">
                <input
                  type="checkbox"
                  checked={Boolean(field.required)}
                  onChange={(e) => updateField(index, { required: e.target.checked })}
                />
                Required
              </label>
            </div>
          ))}
        </div>
      )}

      <details className="text-xs text-on-surface-variant dark:text-molten-text-muted">
        <summary className="cursor-pointer font-semibold text-primary dark:text-molten-primary">View generated JSON</summary>
        <pre className="mt-2 p-3 rounded-lg bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] overflow-x-auto text-[11px] font-mono whitespace-pre-wrap">
          {finalizedPreview}
        </pre>
      </details>
    </div>
  );
}

// Exported for save path if parent wants finalized schema
export { toSchemaJson, parseSchema };
