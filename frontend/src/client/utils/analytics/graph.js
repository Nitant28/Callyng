import { DATE_PERIODS } from './constants.js';
import { getDayKey, getHourKey, isInterestedOutcome, parseTimestamp } from './helpers.js';

const DAY_MS = 24 * 60 * 60 * 1000;
const HOUR_MS = 60 * 60 * 1000;

const startOfDay = (ts) => {
  const d = new Date(ts);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
};

const getRangeWindow = (period, customStart, customEnd) => {
  const now = Date.now();

  if (period === 'today') {
    return { start: startOfDay(now), end: now, unit: 'hour' };
  }

  if (period === 'yesterday') {
    const start = startOfDay(now) - DAY_MS;
    return { start, end: start + DAY_MS, unit: 'hour' };
  }

  if (period === 'custom' && customStart && customEnd) {
    const start = startOfDay(new Date(customStart).getTime());
    const end = new Date(customEnd);
    end.setHours(23, 59, 59, 999);
    const durationMs = Math.max(1, end.getTime() - start);
    return {
      start,
      end: end.getTime(),
      unit: durationMs <= 2 * DAY_MS ? 'hour' : 'day',
    };
  }

  const rangeDays = { '2d': 2, '3d': 3, '7d': 7, '14d': 14, '30d': 30, '90d': 90 }[period] || 7;
  return { start: startOfDay(now - (rangeDays - 1) * DAY_MS), end: now, unit: 'day' };
};

const buildHourBuckets = (start, end) => {
  const buckets = new Map();
  const startHour = new Date(start);
  startHour.setMinutes(0, 0, 0);
  let cursor = startHour.getTime();
  while (cursor <= end) {
    const label = getHourKey(cursor);
    buckets.set(label, { label, interested: 0, totalCalls: 0, timestamp: cursor });
    cursor += HOUR_MS;
  }
  return buckets;
};

const buildDayBuckets = (start, end) => {
  const buckets = new Map();
  let cursor = startOfDay(start);
  const endDay = startOfDay(end);
  while (cursor <= endDay) {
    buckets.set(cursor, {
      label: getDayKey(cursor),
      interested: 0,
      totalCalls: 0,
      timestamp: cursor,
    });
    cursor += DAY_MS;
  }
  return buckets;
};

const bucketCalls = (calls = [], options = {}) => {
  const { period, customStart, customEnd } = options;
  const range = getRangeWindow(period, customStart, customEnd);
  const buckets =
    range.unit === 'hour'
      ? buildHourBuckets(range.start, range.end)
      : buildDayBuckets(range.start, range.end);

  calls.forEach((call) => {
    const timestamp = parseTimestamp(call);
    if (timestamp === null || timestamp < range.start || timestamp > range.end) return;

    if (range.unit === 'hour') {
      const label = getHourKey(timestamp);
      const bucket = buckets.get(label);
      if (!bucket) return;
      bucket.totalCalls += 1;
      if (isInterestedOutcome(call)) bucket.interested += 1;
    } else {
      const dayKey = startOfDay(timestamp);
      if (!buckets.has(dayKey)) {
        buckets.set(dayKey, {
          label: getDayKey(dayKey),
          interested: 0,
          totalCalls: 0,
          timestamp: dayKey,
        });
      }
      const bucket = buckets.get(dayKey);
      bucket.totalCalls += 1;
      if (isInterestedOutcome(call)) bucket.interested += 1;
    }
  });

  return Array.from(buckets.values())
    .sort((a, b) => a.timestamp - b.timestamp)
    .map(({ label, interested, totalCalls }) => ({
      label,
      interested,
      totalCalls,
      calls: interested,
    }));
};

export const buildGraphData = (calls = [], options = {}) => {
  if (!Array.isArray(calls) || calls.length === 0) return [];
  return bucketCalls(calls, options);
};

export const resolvePeriodLabel = (period) =>
  DATE_PERIODS.includes(period) ? period : 'today';
