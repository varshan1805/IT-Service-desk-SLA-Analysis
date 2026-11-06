-- 03_clean.sql
-- Builds the clean tables in public.* from raw.*
-- Fixes, in order:
--   1. drop exact duplicate rows from the export
--   2. tidy category text (case and trailing spaces)
--   3. take resolved/closed times from the audit log, which fixes the
--      UTC bug in the monitoring integration (see 02_data_quality_checks.sql, check 4)
-- Then builds ticket_facts: one row per ticket with every measure the
-- analysis needs, so nobody has to re-derive SLA logic in five places.

DROP TABLE IF EXISTS ticket_facts, ticket_events, tickets, agents, employees,
                     assignment_groups, sla_policy, holidays CASCADE;

CREATE TABLE employees AS SELECT DISTINCT * FROM raw.employees;
ALTER TABLE employees ADD PRIMARY KEY (employee_id);

CREATE TABLE assignment_groups AS SELECT DISTINCT * FROM raw.assignment_groups;
ALTER TABLE assignment_groups ADD PRIMARY KEY (assignment_group);

CREATE TABLE agents AS SELECT DISTINCT * FROM raw.agents;
ALTER TABLE agents ADD PRIMARY KEY (agent_id);
ALTER TABLE agents ADD FOREIGN KEY (assignment_group) REFERENCES assignment_groups;

CREATE TABLE sla_policy AS SELECT DISTINCT * FROM raw.sla_policy;
ALTER TABLE sla_policy ADD PRIMARY KEY (priority);

-- Public holidays the client observes (Tamil Nadu calendar plus national).
-- L1 runs Saturday hours on these days.
CREATE TABLE holidays (holiday_date DATE PRIMARY KEY, holiday_name TEXT);
INSERT INTO holidays VALUES
    ('2025-01-01', 'New Year'),          ('2025-01-14', 'Pongal'),
    ('2025-01-15', 'Thiruvalluvar Day'), ('2025-01-26', 'Republic Day'),
    ('2025-03-31', 'Ramzan'),            ('2025-04-14', 'Tamil New Year'),
    ('2025-04-18', 'Good Friday'),       ('2025-05-01', 'May Day'),
    ('2025-08-15', 'Independence Day'),  ('2025-08-27', 'Vinayagar Chathurthi'),
    ('2025-10-01', 'Ayudha Pooja'),      ('2025-10-02', 'Gandhi Jayanthi'),
    ('2025-10-20', 'Deepavali'),         ('2025-12-25', 'Christmas');


-- Events first, because the ticket fix depends on them
CREATE TABLE ticket_events AS SELECT DISTINCT * FROM raw.ticket_events;
ALTER TABLE ticket_events ADD PRIMARY KEY (event_id);
CREATE INDEX ON ticket_events (ticket_id, event_time);


CREATE TABLE tickets AS
WITH deduped AS (
    SELECT DISTINCT * FROM raw.tickets
),
audit_times AS (
    SELECT ticket_id,
           MAX(event_time) FILTER (WHERE event_type = 'Resolved') AS resolved_at,
           MAX(event_time) FILTER (WHERE event_type IN ('Closed', 'Cancelled')) AS closed_at
    FROM ticket_events
    GROUP BY ticket_id
)
SELECT d.ticket_id,
       d.opened_at,
       d.channel,
       d.requester_id,
       INITCAP(TRIM(d.category)) AS category,
       d.subcategory,
       d.priority,
       d.short_description,
       d.status,
       d.assignment_group,
       d.assigned_to,
       d.first_response_at,
       CASE WHEN d.resolved_at IS NULL THEN NULL ELSE a.resolved_at END AS resolved_at,
       CASE WHEN d.closed_at   IS NULL THEN NULL ELSE a.closed_at   END AS closed_at,
       d.reassignment_count,
       d.reopen_count,
       d.work_minutes,
       d.resolution_code,
       d.csat_score,
       (d.resolved_at IS DISTINCT FROM a.resolved_at AND d.resolved_at IS NOT NULL) AS time_fixed_from_audit
FROM deduped d
LEFT JOIN audit_times a USING (ticket_id);

ALTER TABLE tickets ADD PRIMARY KEY (ticket_id);
ALTER TABLE tickets ADD FOREIGN KEY (assignment_group) REFERENCES assignment_groups;
ALTER TABLE tickets ADD FOREIGN KEY (assigned_to) REFERENCES agents;
ALTER TABLE tickets ADD FOREIGN KEY (requester_id) REFERENCES employees;
ALTER TABLE tickets ADD FOREIGN KEY (priority) REFERENCES sla_policy;
ALTER TABLE ticket_events ADD FOREIGN KEY (ticket_id) REFERENCES tickets;


-- One row per ticket, all the SLA logic in one place
CREATE TABLE ticket_facts AS
WITH bounce_counts AS (
    -- A "bounce" is an L2 team that had the ticket but wasn't the team that fixed it.
    -- The normal L1 -> L2 handoff is not a bounce.
    SELECT e.ticket_id,
           COUNT(DISTINCT e.assignment_group) AS groups_touched,
           COUNT(DISTINCT e.assignment_group) FILTER (
               WHERE e.assignment_group <> t.assignment_group
                 AND e.assignment_group <> 'Service Desk L1'
           ) AS bounces
    FROM ticket_events e
    JOIN tickets t USING (ticket_id)
    WHERE e.event_type = 'Assigned'
    GROUP BY e.ticket_id
),
base AS (
    SELECT t.*,
           emp.department,
           emp.location,
           COALESCE(emp.site_type, 'System') AS site_type,
           g.tier AS resolver_tier,
           s.response_target_min,
           s.resolution_target_hours,
           s.monthly_target_pct,
           COALESCE(b.groups_touched, 0) AS groups_touched,
           COALESCE(b.bounces, 0) AS bounces,
           EXTRACT(EPOCH FROM (t.first_response_at - t.opened_at)) / 60.0  AS response_minutes,
           EXTRACT(EPOCH FROM (t.resolved_at - t.opened_at)) / 3600.0      AS resolution_hours,
           h.holiday_date IS NOT NULL AS opened_on_holiday
    FROM tickets t
    JOIN sla_policy s USING (priority)
    JOIN assignment_groups g ON g.assignment_group = t.assignment_group
    LEFT JOIN employees emp ON emp.employee_id = t.requester_id
    LEFT JOIN bounce_counts b USING (ticket_id)
    LEFT JOIN holidays h ON h.holiday_date = t.opened_at::date
)
SELECT ticket_id,
       opened_at,
       opened_at::date                               AS opened_date,
       DATE_TRUNC('month', opened_at)::date          AS opened_month,
       EXTRACT(HOUR FROM opened_at)::int             AS opened_hour,
       EXTRACT(ISODOW FROM opened_at)::int           AS opened_isodow,   -- 1 = Monday
       TO_CHAR(opened_at, 'Dy')                      AS opened_weekday,
       channel, requester_id, department, location, site_type,
       category, subcategory, priority, status,
       assignment_group AS resolving_group,
       resolver_tier,
       assigned_to,
       first_response_at, resolved_at, closed_at,
       ROUND(response_minutes::numeric, 1)  AS response_minutes,
       ROUND(resolution_hours::numeric, 2)  AS resolution_hours,
       response_target_min, resolution_target_hours, monthly_target_pct,

       -- Cancelled tickets are out of SLA scope, so they stay NULL here
       CASE WHEN status = 'Cancelled' THEN NULL
            WHEN first_response_at IS NULL THEN NULL
            ELSE response_minutes <= response_target_min END                    AS met_response_sla,

       -- Still-open tickets that are already past target count as breached.
       -- Still-open tickets inside target are unknown (NULL), not "met".
       CASE WHEN status = 'Cancelled' THEN NULL
            WHEN resolved_at IS NOT NULL THEN resolution_hours <= resolution_target_hours
            WHEN EXTRACT(EPOCH FROM (TIMESTAMP '2026-01-02 09:00' - opened_at)) / 3600.0
                 > resolution_target_hours THEN FALSE
            ELSE NULL END                                                        AS met_resolution_sla,

       groups_touched,
       bounces,
       bounces > 0          AS was_bounced,
       reopen_count,
       reopen_count > 0     AS was_reopened,
       work_minutes,
       csat_score,
       resolution_code,
       time_fixed_from_audit,

       -- Was L1 off shift when the ticket came in?
       -- L1: Mon-Fri 08-20, Sat 09-14 (holidays too), Sunday closed.
       CASE
           WHEN channel = 'Monitoring' THEN FALSE   -- alerts go straight to 24x7 teams
           WHEN EXTRACT(ISODOW FROM opened_at) = 7 THEN TRUE
           WHEN EXTRACT(ISODOW FROM opened_at) = 6 OR opened_on_holiday
               THEN NOT (EXTRACT(HOUR FROM opened_at) BETWEEN 9 AND 13)
           ELSE NOT (EXTRACT(HOUR FROM opened_at) BETWEEN 8 AND 19)
       END AS opened_after_hours,

       (EXTRACT(DAY FROM opened_at) >= 28 OR EXTRACT(DAY FROM opened_at) <= 2) AS is_month_end_window
FROM base;

ALTER TABLE ticket_facts ADD PRIMARY KEY (ticket_id);
CREATE INDEX ON ticket_facts (opened_month, priority);

-- Quick sanity line so the loader prints something useful
SELECT COUNT(*) AS tickets,
       COUNT(*) FILTER (WHERE time_fixed_from_audit) AS times_fixed_from_audit,
       COUNT(*) FILTER (WHERE resolution_hours < 0) AS negative_durations_left
FROM ticket_facts;
