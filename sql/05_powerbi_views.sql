-- 05_powerbi_views.sql
-- Star schema for Power BI. Connect Power BI to the pbi schema only, so the
-- report never depends on raw or half-built tables.
--
--   fact_ticket       one row per ticket
--   fact_group_time   one row per stretch of time a ticket sat with a team
--   dim_date, dim_priority, dim_group, dim_agent, dim_employee
--   monthly_sla       month x priority compliance and service credits
--                     (Power BI recalculates this in DAX; this view is for
--                     reconciling the two so I know the DAX is right)

DROP SCHEMA IF EXISTS pbi CASCADE;
CREATE SCHEMA pbi;

CREATE VIEW pbi.fact_ticket AS
WITH first_l2 AS (
    -- First L2 team that picked the ticket up. If it isn't the resolving
    -- team, this is where the ticket bounced first.
    SELECT DISTINCT ON (ticket_id) ticket_id, assignment_group AS first_l2_team
    FROM ticket_events
    WHERE event_type = 'Assigned' AND assignment_group <> 'Service Desk L1'
    ORDER BY ticket_id, event_time, event_id
)
SELECT f.ticket_id, f.opened_at, f.opened_date, f.opened_hour, f.opened_isodow,
       f.channel, f.requester_id, f.site_type, f.category, f.subcategory, f.priority, f.status,
       f.resolving_group, fl.first_l2_team, f.assigned_to,
       f.response_minutes, f.resolution_hours,
       f.met_response_sla, f.met_resolution_sla,
       f.bounces, f.was_bounced, f.reopen_count, f.was_reopened,
       f.work_minutes, f.csat_score, f.resolution_code,
       f.opened_after_hours, f.is_month_end_window
FROM ticket_facts f
LEFT JOIN first_l2 fl USING (ticket_id);

CREATE VIEW pbi.dim_priority AS
SELECT priority, response_target_min, resolution_target_hours, monthly_target_pct
FROM sla_policy;

CREATE VIEW pbi.dim_date AS
SELECT d::date                               AS date,
       EXTRACT(YEAR FROM d)::int             AS year,
       EXTRACT(MONTH FROM d)::int            AS month_no,
       TO_CHAR(d, 'Mon')                     AS month_name,
       DATE_TRUNC('month', d)::date          AS month_start,
       EXTRACT(WEEK FROM d)::int             AS iso_week,
       DATE_TRUNC('week', d)::date           AS week_start,
       EXTRACT(ISODOW FROM d)::int           AS weekday_no,
       TO_CHAR(d, 'Dy')                      AS weekday_name,
       EXTRACT(ISODOW FROM d) IN (6, 7)      AS is_weekend,
       h.holiday_date IS NOT NULL            AS is_holiday,
       h.holiday_name
FROM generate_series(DATE '2025-01-01', DATE '2026-01-02', INTERVAL '1 day') AS d
LEFT JOIN holidays h ON h.holiday_date = d::date;

CREATE VIEW pbi.dim_group AS
SELECT assignment_group, tier, shift_pattern, is_24x7, headcount
FROM assignment_groups;

CREATE VIEW pbi.dim_agent AS
SELECT agent_id, agent_name, assignment_group, tier, joined_on
FROM agents;

CREATE VIEW pbi.dim_employee AS
SELECT employee_id, department, location, site_type
FROM employees;

-- Where does the time go? Each event starts a stretch that lasts until the next event.
--   Created / Reassigned / Reopened -> ticket is sitting in that team's queue
--   Assigned                        -> an agent in that team has it
-- Time after Resolved isn't counted (that's the user's confirmation window).
CREATE VIEW pbi.fact_group_time AS
WITH ordered AS (
    SELECT e.ticket_id,
           e.event_type,
           e.assignment_group,
           e.event_time,
           LEAD(e.event_time) OVER (PARTITION BY e.ticket_id ORDER BY e.event_time, e.event_id) AS next_event_time
    FROM ticket_events e
)
SELECT o.ticket_id,
       o.assignment_group,
       CASE WHEN o.event_type = 'Assigned' THEN 'With agent' ELSE 'In queue' END AS state,
       o.assignment_group <> f.resolving_group
           AND o.assignment_group <> 'Service Desk L1'                         AS is_wrong_team,
       o.event_time AS started_at,
       ROUND((EXTRACT(EPOCH FROM (o.next_event_time - o.event_time)) / 3600.0)::numeric, 3) AS hours
FROM ordered o
JOIN ticket_facts f USING (ticket_id)
WHERE o.event_type IN ('Created', 'Reassigned', 'Reopened', 'Assigned')
  AND o.next_event_time IS NOT NULL;

CREATE VIEW pbi.monthly_sla AS
WITH monthly AS (
    SELECT opened_month,
           priority,
           MAX(monthly_target_pct) AS target_pct,
           COUNT(*) FILTER (WHERE met_resolution_sla IS NOT NULL) AS tickets_in_scope,
           COUNT(*) FILTER (WHERE met_resolution_sla)             AS tickets_met,
           COUNT(*) FILTER (WHERE NOT met_resolution_sla)         AS tickets_breached
    FROM ticket_facts
    GROUP BY opened_month, priority
),
scored AS (
    SELECT *,
           ROUND(100.0 * tickets_met / NULLIF(tickets_in_scope, 0), 2) AS compliance_pct
    FROM monthly
)
SELECT s.*,
       s.compliance_pct < s.target_pct AS missed_target,
       COUNT(*) FILTER (WHERE s.compliance_pct < s.target_pct)
           OVER (PARTITION BY s.opened_month) AS priorities_missed_in_month,
       -- 2.5% of the 38 lakh fee per missed priority, capped at 10% a month
       ROUND(LEAST(10.0, 2.5 * COUNT(*) FILTER (WHERE s.compliance_pct < s.target_pct)
           OVER (PARTITION BY s.opened_month)) / 100.0 * 3800000)::bigint AS month_service_credit_inr
FROM scored s;
