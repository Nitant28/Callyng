/**
 * Date range helpers for charts and activity feeds.
 */

const DAY = 24 * 60 * 60 * 1000;

export const CHART_RANGES = [
  { id: 'today', label: 'Today' },
  { id: 'yesterday', label: 'Yesterday' },
  { id: '3d', label: 'Last 3 Days' },
  { id: '7d', label: 'Last 7 Days' },
  { id: '14d', label: 'Last 14 Days' },
  { id: '30d', label: 'Last 30 Days' },
  { id: '90d', label: 'Last 90 Days' },
];

export const ACTIVITY_RANGES = [
  { id: 'today', label: 'Today' },
  { id: 'yesterday', label: 'Yesterday' },
  { id: '3d', label: 'Last 3 Days' },
  { id: 'week', label: 'Last Week' },
  { id: 'month', label: 'Last Month' },
];

function rangeBounds(rangeId) {
  const now = Date.now();
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);

  switch (rangeId) {
    case 'today':
      return { start: startOfToday.getTime(), end: now };
    case 'yesterday': {
      const start = new Date(startOfToday);
      start.setDate(start.getDate() - 1);
      return { start: start.getTime(), end: startOfToday.getTime() };
    }
    case '3d':
      return { start: now - 3 * DAY, end: now };
    case '7d':
    case 'week':
      return { start: now - 7 * DAY, end: now };
    case '14d':
      return { start: now - 14 * DAY, end: now };
    case '30d':
    case 'month':
      return { start: now - 30 * DAY, end: now };
    case '90d':
      return { start: now - 90 * DAY, end: now };
    default:
      return { start: now - 7 * DAY, end: now };
  }
}

export function isInRange(iso, rangeId) {
  if (!iso) return false;
  const t = new Date(iso).getTime();
  const { start, end } = rangeBounds(rangeId);
  return t >= start && t <= end;
}

export function bucketCallsByRange(calls, rangeId = '7d') {
  const { start } = rangeBounds(rangeId);
  const buckets = {};

  (calls ?? []).forEach((call) => {
    if (!call?.createdAt) return;
    const t = new Date(call.createdAt).getTime();
    if (t < start) return;
    const d = new Date(t);
    const key = `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:00`;
    buckets[key] = (buckets[key] || 0) + 1;
  });

  return Object.entries(buckets)
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => a.label.localeCompare(b.label));
}
