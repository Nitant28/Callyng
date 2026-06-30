-- Test queries to verify dialer partial indexes
SET enable_seqscan = OFF;

-- 1. Live-call NOT EXISTS (15 min grace)
EXPLAIN (ANALYZE, BUFFERS)
SELECT 1 FROM call_logs c
WHERE c.lead_id = '00000000-0000-4000-8000-000000000007'
  AND c.in_progress = TRUE
  AND c.started_at > NOW() - (15 * INTERVAL '1 minute');

-- 2. Wrap-up NOT EXISTS (5 min grace)
EXPLAIN (ANALYZE, BUFFERS)
SELECT 1 FROM call_logs c
WHERE c.lead_id = '00000000-0000-4000-8000-000000000007'
  AND c.ended_at IS NOT NULL
  AND c.ended_at > NOW() - (5 * INTERVAL '1 minute');
