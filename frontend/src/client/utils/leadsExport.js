/** Build CSV export: original imported fields (name/phone + metadata) + system columns. */

function parseMetadata(raw) {
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) return raw;
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

function csvEscape(value) {
  const str = value == null ? '' : String(value);
  if (/[",\n\r]/.test(str)) return `"${str.replace(/"/g, '""')}"`;
  return str;
}

function metaValue(meta, key) {
  if (key in meta && meta[key] != null) return meta[key];
  const lower = String(key).toLowerCase();
  for (const [mk, mv] of Object.entries(meta)) {
    if (String(mk).toLowerCase() === lower && mv != null) return mv;
  }
  return '';
}

/**
 * @param {Array<object>} rows - lead rows from list API (includes metadata)
 * @returns {string} CSV content
 */
export function buildLeadsExportCsv(rows = []) {
  const metaKeyOrder = [];
  const seen = new Set();

  (rows || []).forEach((row) => {
    Object.keys(parseMetadata(row.metadata)).forEach((key) => {
      const lower = String(key).toLowerCase();
      if (lower === 'phone' || lower === 'name' || lower === 'lead_type') return;
      if (!seen.has(lower)) {
        seen.add(lower);
        metaKeyOrder.push(key);
      }
    });
  });

  const systemCols = [
    { header: 'Status', get: (r) => r.status || '' },
    { header: 'Outcome', get: (r) => r.outcome || '' },
    { header: 'Attempts', get: (r) => r.attempts ?? 0 },
    { header: 'Turns', get: (r) => (r.transcript_turns != null ? r.transcript_turns : '') },
    {
      header: 'Interested',
      get: (r) => ((r.outcome || '').trim() === 'Interested' ? 'Yes' : 'No'),
    },
    {
      header: 'Last Call Duration',
      get: (r) => r.last_call_duration_seconds ?? '',
    },
    {
      header: 'Last Call',
      get: (r) => r.last_call_ended_at || r.last_attempted_at || '',
    },
    { header: 'Created Time', get: (r) => r.created_at || '' },
    { header: 'Updated Time', get: (r) => r.updated_at || '' },
  ];

  const headers = [
    'Name',
    'Phone',
    ...metaKeyOrder,
    ...systemCols.map((c) => c.header),
  ];

  const lines = [headers.map(csvEscape).join(',')];

  (rows || []).forEach((row) => {
    const meta = parseMetadata(row.metadata);
    const cells = [
      row.name || '',
      row.phone || '',
      ...metaKeyOrder.map((key) => metaValue(meta, key)),
      ...systemCols.map((c) => c.get(row)),
    ];
    lines.push(cells.map(csvEscape).join(','));
  });

  return lines.join('\r\n');
}

export function downloadCsv(filename, csvContent) {
  const blob = new Blob([`\uFEFF${csvContent}`], { type: 'text/csv;charset=utf-8;' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}
