-- 02_data_quality_checks.sql
-- Run these against raw.* before trusting any number.
-- Each check says what I was looking for and what I found.


-- 1. Row counts vs distinct ticket ids
--    Found: about 170 more rows than tickets. The export wrote some rows twice.
SELECT COUNT(*)                   AS total_rows,
       COUNT(DISTINCT ticket_id)  AS distinct_tickets,
       COUNT(*) - COUNT(DISTINCT ticket_id) AS duplicate_rows
FROM raw.tickets;

-- Are the duplicates exact copies, or two different versions of a ticket?
-- If any row came back here, I'd have to pick a version instead of just dropping one.
SELECT ticket_id, COUNT(DISTINCT (status, resolved_at, assignment_group, csat_score)) AS versions
FROM raw.tickets
GROUP BY ticket_id
HAVING COUNT(*) > 1
   AND COUNT(DISTINCT (status, resolved_at, assignment_group, csat_score)) > 1;
-- Found: no rows. All duplicates are exact copies, safe to drop.


-- 2. Category values. There should be 8.
--    Found: lower-case versions and versions with a trailing space.
SELECT category, LENGTH(category) AS len, COUNT(*) AS tickets
FROM raw.tickets
GROUP BY category
ORDER BY LOWER(TRIM(category)), category;


-- 3. Tickets resolved before they were opened
--    Found: a few hundred, and they are not random.
SELECT channel,
       DATE_TRUNC('month', opened_at)::date AS month_opened,
       COUNT(*) AS negative_durations
FROM raw.tickets
WHERE resolved_at < opened_at
GROUP BY 1, 2
ORDER BY 1, 2;
-- Every one is a Monitoring ticket opened in March or early April.
-- That smells like a time zone problem in the monitoring integration.


-- 4. Prove the time zone theory using the audit log (ticket_events).
--    The event log is written by the platform itself, so I trust it more
--    than the resolved_at field the integration writes.
WITH last_resolve AS (
    SELECT ticket_id, MAX(event_time) AS resolved_event_time
    FROM raw.ticket_events
    WHERE event_type = 'Resolved'
    GROUP BY ticket_id
),
t AS (
    SELECT DISTINCT ON (ticket_id) *
    FROM raw.tickets
    ORDER BY ticket_id
)
SELECT t.channel,
       (t.opened_at BETWEEN '2025-03-01' AND '2025-04-15 23:59:59') AS in_suspect_window,
       l.resolved_event_time - t.resolved_at AS gap,
       COUNT(*) AS tickets
FROM t
JOIN last_resolve l USING (ticket_id)
WHERE t.resolved_at IS NOT NULL
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;
-- Found: gap is exactly 05:30:00 for Monitoring tickets in that window and
-- 00:00:00 for everything else. UTC vs IST, confirmed. The bad rows also
-- include tickets that don't show a negative duration, which is why fixing
-- only the negative ones would have been wrong.


-- 5. Status vs timestamps should agree
SELECT status,
       COUNT(*) FILTER (WHERE resolved_at IS NULL)        AS no_resolved_time,
       COUNT(*) FILTER (WHERE first_response_at IS NULL)  AS no_response_time,
       COUNT(*) FILTER (WHERE closed_at IS NULL)          AS no_closed_time,
       COUNT(*)                                           AS tickets
FROM (SELECT DISTINCT * FROM raw.tickets) t
GROUP BY status;
-- Found: Cancelled tickets have no response or resolve time (expected).
-- Resolved = not auto-closed yet. In Progress = still open at export time.


-- 6. Every ticket should have a Created event and events in time order
SELECT COUNT(*) AS tickets_without_created_event
FROM (SELECT DISTINCT ticket_id FROM raw.tickets) t
WHERE NOT EXISTS (
    SELECT 1 FROM raw.ticket_events e
    WHERE e.ticket_id = t.ticket_id AND e.event_type = 'Created'
);


-- 7. Orphans: agents and requesters that don't exist in the master tables
SELECT 'assigned_to not in agents' AS check_name, COUNT(*) AS rows_found
FROM raw.tickets t
WHERE t.assigned_to IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM raw.agents a WHERE a.agent_id = t.assigned_to)
UNION ALL
SELECT 'requester not in employees', COUNT(*)
FROM raw.tickets t
WHERE t.requester_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM raw.employees e WHERE e.employee_id = t.requester_id);


-- 8. CSAT coverage. Low response rates make CSAT easy to over-read.
SELECT COUNT(*) FILTER (WHERE csat_score IS NOT NULL) AS surveys_answered,
       COUNT(*) FILTER (WHERE status IN ('Resolved', 'Closed')) AS resolved_tickets,
       ROUND(100.0 * COUNT(*) FILTER (WHERE csat_score IS NOT NULL)
             / NULLIF(COUNT(*) FILTER (WHERE status IN ('Resolved', 'Closed')), 0), 1) AS response_rate_pct
FROM (SELECT DISTINCT * FROM raw.tickets) t;
