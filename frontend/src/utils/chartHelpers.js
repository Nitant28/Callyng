/**
 * Chart helpers — smooth display interpolation only; totals stay from real data.
 */

const RANGE_MS = {
  '24h': 24 * 60 * 60 * 1000,
  week: 7 * 24 * 60 * 60 * 1000,
  month: 30 * 24 * 60 * 60 * 1000,
  quarter: 90 * 24 * 60 * 60 * 1000,
};

export function bucketCallsByHour(calls, rangeId = 'week') {
  const now = Date.now();
  const windowMs = RANGE_MS[rangeId] ?? RANGE_MS.week;
  const start = now - windowMs;

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
    .map(([label, count]) => ({ label, count, raw: count }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

/** Add interpolated display points between sparse real buckets (visual only). */
export function smoothChartSeries(points, minPoints = 12) {
  if (!points.length) return [];
  if (points.length >= minPoints) return points;

  const result = [];
  const target = Math.max(minPoints, points.length * 4);

  for (let i = 0; i < points.length - 1; i += 1) {
    const a = points[i];
    const b = points[i + 1];
    result.push({ ...a, display: a.count });

    const steps = Math.ceil(target / (points.length - 1)) - 1;
    for (let s = 1; s <= steps; s += 1) {
      const t = s / (steps + 1);
      const eased = t * t * (3 - 2 * t);
      const display = Math.round(a.count + (b.count - a.count) * eased);
      result.push({
        label: `${a.label} → ${b.label}`,
        count: display,
        display,
        interpolated: true,
      });
    }
  }

  const last = points[points.length - 1];
  result.push({ ...last, display: last.count });
  return result;
}

export function last7DaySeries(calls) {
  const days = [];
  const now = new Date();
  for (let i = 6; i >= 0; i -= 1) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    d.setHours(0, 0, 0, 0);
    const key = d.toISOString().slice(0, 10);
    days.push({ key, count: 0 });
  }

  const map = Object.fromEntries(days.map((d) => [d.key, 0]));
  (calls ?? []).forEach((call) => {
    if (!call?.createdAt) return;
    const key = new Date(call.createdAt).toISOString().slice(0, 10);
    if (key in map) map[key] += 1;
  });

  return days.map((d) => map[d.key]);
}

export function computeTrendPercent(series) {
  if (!series?.length || series.length < 2) return null;
  const mid = Math.floor(series.length / 2);
  const prev = series.slice(0, mid).reduce((s, n) => s + n, 0);
  const curr = series.slice(mid).reduce((s, n) => s + n, 0);
  if (prev === 0 && curr === 0) return null;
  if (prev === 0) return { value: 100, direction: 'up' };
  const pct = ((curr - prev) / prev) * 100;
  return {
    value: Math.abs(pct).toFixed(1),
    direction: pct >= 0 ? 'up' : 'down',
  };
}

export function chartSummaryFromCalls(calls, rangeId = 'week') {
  const buckets = bucketCallsByHour(calls, rangeId);
  const total = buckets.reduce((s, b) => s + b.count, 0);
  const series = buckets.map((b) => b.count);
  const trend = computeTrendPercent(series.length ? series : last7DaySeries(calls));
  return { total, trend, buckets };
}
