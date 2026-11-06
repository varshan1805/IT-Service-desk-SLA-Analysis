-- 04_analysis_queries.sql
-- The business questions, in the order I worked through them.
-- Everything reads from ticket_facts (built in 03_clean.sql) or the events log.


-- Q1. How bad is it? Monthly resolution SLA by priority, and what it cost.
--     The contract pays back 2.5% of the monthly fee for every priority that
--     misses its target that month, capped at 10%.
SELECT opened_month,
       priority,
       tickets_in_scope,
       compliance_pct,
       target_pct,
       CASE WHEN missed_target THEN 'MISSED' ELSE 'ok' END AS result,
       month_service_credit_inr
FROM pbi.monthly_sla
ORDER BY opened_month, priority;

-- Year total of credits (one row per month, so take the month value once)
SELECT COUNT(*)                         AS months,
       SUM(credit)                      AS total_credit_inr,
       ROUND(AVG(credit))               AS avg_monthly_credit_inr
FROM (
    SELECT DISTINCT opened_month, month_service_credit_inr AS credit
    FROM pbi.monthly_sla
) m;

-- Which priority misses most often?
SELECT priority,
       COUNT(*) FILTER (WHERE missed_target) AS months_missed,
       ROUND(AVG(compliance_pct), 1)         AS avg_compliance_pct,
       MAX(target_pct)                       AS target_pct
FROM pbi.monthly_sla
GROUP BY priority
ORDER BY priority;


-- Q2. Pareto: which subcategories produce most of the breaches?
SELECT subcategory,
       breaches,
       ROUND(100.0 * breaches / SUM(breaches) OVER (), 1)                         AS pct_of_breaches,
       ROUND(100.0 * SUM(breaches) OVER (ORDER BY breaches DESC, subcategory)
             / SUM(breaches) OVER (), 1)                                          AS cumulative_pct,
       ROUND(100.0 * breaches / tickets, 1)                                       AS breach_rate_pct
FROM (
    SELECT subcategory,
           COUNT(*) FILTER (WHERE met_resolution_sla = FALSE) AS breaches,
           COUNT(*) FILTER (WHERE met_resolution_sla IS NOT NULL) AS tickets
    FROM ticket_facts
    GROUP BY subcategory
) s
ORDER BY breaches DESC;


-- Q3. Does sending a ticket to the wrong team first actually matter?
SELECT LEAST(bounces, 2)                                            AS bounces,   -- 2 = "2 or more"
       COUNT(*)                                                     AS tickets,
       ROUND(100.0 * AVG((NOT met_resolution_sla)::int), 1)         AS breach_rate_pct,
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY resolution_hours)::numeric, 1) AS median_hours,
       ROUND(AVG(csat_score), 2)                                    AS avg_csat
FROM ticket_facts
WHERE met_resolution_sla IS NOT NULL
GROUP BY 1
ORDER BY 1;

-- Share of all breaches that went through at least one wrong team
SELECT COUNT(*) FILTER (WHERE was_bounced)                        AS bounced_breaches,
       COUNT(*)                                                   AS all_breaches,
       ROUND(100.0 * COUNT(*) FILTER (WHERE was_bounced) / COUNT(*), 1) AS pct_of_breaches,
       (SELECT ROUND(100.0 * AVG(was_bounced::int), 1)
          FROM ticket_facts WHERE met_resolution_sla IS NOT NULL) AS pct_of_tickets
FROM ticket_facts
WHERE met_resolution_sla = FALSE;

-- Fair comparison: same priority, same subcategory, bounced vs not.
-- If bounced tickets were just "harder" tickets, this gap would shrink.
SELECT priority,
       subcategory,
       COUNT(*) FILTER (WHERE was_bounced)                                         AS bounced_n,
       ROUND(100.0 * AVG((NOT met_resolution_sla)::int) FILTER (WHERE was_bounced), 1)     AS bounced_breach_pct,
       ROUND(100.0 * AVG((NOT met_resolution_sla)::int) FILTER (WHERE NOT was_bounced), 1) AS direct_breach_pct
FROM ticket_facts
WHERE met_resolution_sla IS NOT NULL
GROUP BY priority, subcategory
HAVING COUNT(*) FILTER (WHERE was_bounced) >= 50
ORDER BY bounced_n DESC;


-- Q4. Where do they bounce? The most common wrong first stop per subcategory.
--     Uses the event log: first L2 team assigned vs the team that fixed it.
WITH first_l2 AS (
    SELECT DISTINCT ON (e.ticket_id)
           e.ticket_id, e.assignment_group AS first_team
    FROM ticket_events e
    WHERE e.event_type = 'Assigned'
      AND e.assignment_group <> 'Service Desk L1'
    ORDER BY e.ticket_id, e.event_time, e.event_id
)
SELECT f.subcategory,
       fl.first_team         AS sent_to,
       f.resolving_group     AS should_have_gone_to,
       COUNT(*)              AS tickets,
       ROUND(AVG(f.resolution_hours), 1) AS avg_hours_to_resolve,
       RANK() OVER (ORDER BY COUNT(*) DESC) AS rnk
FROM ticket_facts f
JOIN first_l2 fl USING (ticket_id)
WHERE fl.first_team <> f.resolving_group
GROUP BY 1, 2, 3
ORDER BY tickets DESC
LIMIT 12;


-- Q5. How many hours did tickets spend sitting with the wrong team?
SELECT state,
       is_wrong_team,
       COUNT(DISTINCT ticket_id)       AS tickets,
       ROUND(SUM(hours))               AS total_hours,
       ROUND(AVG(hours), 1)            AS avg_hours_per_stretch
FROM pbi.fact_group_time
GROUP BY state, is_wrong_team
ORDER BY is_wrong_team DESC, state;


-- Q6. The night gap. First response SLA by hour the ticket came in, offices vs warehouses.
SELECT opened_hour,
       site_type,
       COUNT(*)                                                   AS tickets,
       ROUND(100.0 * AVG(met_response_sla::int), 1)               AS response_sla_met_pct,
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY response_minutes)::numeric) AS median_response_min
FROM ticket_facts
WHERE met_response_sla IS NOT NULL
  AND site_type IN ('Office', 'Warehouse')
GROUP BY opened_hour, site_type
ORDER BY site_type, opened_hour;

-- Same thing summed up: tickets raised while L1 was off shift
SELECT site_type,
       opened_after_hours,
       COUNT(*)                                                   AS tickets,
       ROUND(100.0 * AVG(met_response_sla::int), 1)               AS response_sla_met_pct,
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY response_minutes)::numeric / 60, 1) AS median_wait_hours
FROM ticket_facts
WHERE met_response_sla IS NOT NULL
  AND site_type IN ('Office', 'Warehouse')
GROUP BY 1, 2
ORDER BY 1, 2;

-- Warehouse staff locked out at night: they can't scan anything until L1 logs in at 8
SELECT subcategory,
       COUNT(*)                                                                        AS night_tickets,
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY resolution_hours)::numeric, 1) AS median_hours_to_fix
FROM ticket_facts
WHERE site_type = 'Warehouse'
  AND opened_after_hours
  AND subcategory IN ('Password reset', 'Account lockout')
  AND resolution_hours IS NOT NULL
GROUP BY subcategory;


-- Q7. Monday mornings. Volume and response by weekday and hour (heatmap data).
SELECT opened_weekday,
       opened_isodow,
       COUNT(*)                                         AS tickets,
       ROUND(COUNT(*)::numeric / COUNT(DISTINCT opened_date), 1) AS tickets_per_day,
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY response_minutes)::numeric) AS median_response_min
FROM ticket_facts
WHERE channel <> 'Monitoring' AND status <> 'Cancelled'
GROUP BY opened_weekday, opened_isodow
ORDER BY opened_isodow;


-- Q8. Reopens. Which team's "fixed" doesn't stay fixed?
SELECT resolving_group,
       COUNT(*)                                          AS resolved_tickets,
       SUM(reopen_count)                                 AS reopens,
       ROUND(100.0 * AVG(was_reopened::int), 1)          AS reopen_rate_pct,
       ROUND(AVG(csat_score) FILTER (WHERE was_reopened), 2)     AS csat_when_reopened,
       ROUND(AVG(csat_score) FILTER (WHERE NOT was_reopened), 2) AS csat_when_not
FROM ticket_facts
WHERE resolved_at IS NOT NULL
GROUP BY resolving_group
ORDER BY reopen_rate_pct DESC;

-- Is it one or two people in Desktop Support, or the whole team?
-- If a couple of agents stood out, it's a coaching problem. If it's flat, it's the process.
SELECT a.agent_name,
       COUNT(*)                                    AS resolved,
       ROUND(100.0 * AVG(f.was_reopened::int), 1)  AS reopen_rate_pct,
       ROUND(100.0 * AVG(f.was_reopened::int)
             - AVG(100.0 * AVG(f.was_reopened::int)) OVER (), 1) AS vs_team_avg,
       NTILE(4) OVER (ORDER BY AVG(f.was_reopened::int) DESC)   AS quartile
FROM ticket_facts f
JOIN agents a ON a.agent_id = f.assigned_to
WHERE f.resolving_group = 'Desktop Support'
  AND f.resolved_at IS NOT NULL
GROUP BY a.agent_name
ORDER BY reopen_rate_pct DESC;


-- Q9. The VPN incident. Weekly VPN volume and how Network Ops coped.
SELECT DATE_TRUNC('week', opened_at)::date                                    AS week_start,
       COUNT(*) FILTER (WHERE subcategory = 'VPN')                            AS vpn_tickets,
       ROUND(100.0 * AVG((NOT met_resolution_sla)::int)
             FILTER (WHERE resolving_group = 'Network Operations'), 1)        AS netops_breach_pct,
       ROUND(100.0 * AVG(was_reopened::int) FILTER (WHERE subcategory = 'VPN'), 1) AS vpn_reopen_pct
FROM ticket_facts
WHERE opened_at >= '2025-06-01' AND opened_at < '2025-10-01'
  AND met_resolution_sla IS NOT NULL
GROUP BY 1
ORDER BY 1;

-- Before / during / after, and how many extra tickets it created
WITH tagged AS (
    SELECT *,
           CASE WHEN opened_at <  '2025-07-14' THEN '1 before'
                WHEN opened_at <  '2025-08-25' THEN '2 during'
                ELSE '3 after' END AS phase
    FROM ticket_facts
    WHERE status <> 'Cancelled'
)
SELECT phase,
       COUNT(DISTINCT opened_date)                                                    AS days,
       ROUND(COUNT(*) FILTER (WHERE subcategory = 'VPN')::numeric / COUNT(DISTINCT opened_date), 1) AS vpn_per_day,
       ROUND(100.0 * AVG((NOT met_resolution_sla)::int)
             FILTER (WHERE resolving_group = 'Network Operations'), 1)                AS netops_breach_pct,
       ROUND(100.0 * AVG((NOT met_resolution_sla)::int)
             FILTER (WHERE resolving_group = 'Network Operations' AND subcategory <> 'VPN'), 1) AS netops_non_vpn_breach_pct
FROM tagged
GROUP BY phase
ORDER BY phase;


-- Q10. Month end. ERP tickets per day, by day of month.
SELECT EXTRACT(DAY FROM opened_at)::int                    AS day_of_month,
       COUNT(*)                                            AS erp_tickets,
       ROUND(COUNT(*)::numeric / COUNT(DISTINCT opened_month), 1) AS avg_per_month,
       COUNT(*) FILTER (WHERE priority IN ('P1', 'P2'))    AS p1_p2
FROM ticket_facts
WHERE subcategory IN ('ERP error', 'ERP performance')
GROUP BY 1
ORDER BY 1;


-- Q11. Password resets and lockouts: how much L1 time do they eat?
--      These are the tickets a self-service reset portal would remove.
SELECT subcategory,
       site_type,
       COUNT(*)                                          AS tickets,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM ticket_facts WHERE status <> 'Cancelled'), 1) AS pct_of_all_tickets,
       ROUND(AVG(work_minutes), 1)                       AS avg_work_min,
       ROUND(SUM(work_minutes) / 60.0)                   AS l1_hours,
       ROUND(SUM(work_minutes) / 60.0 * 420)             AS l1_cost_inr,      -- 420/hr, see settings.py
       COUNT(*) FILTER (WHERE opened_after_hours)        AS raised_while_l1_closed
FROM ticket_facts
WHERE status <> 'Cancelled'
  AND subcategory IN ('Password reset', 'Account lockout')
GROUP BY ROLLUP (subcategory, site_type)
ORDER BY subcategory NULLS LAST, site_type NULLS LAST;


-- Q12. What drives CSAT? (only about 1 in 5 users answer, so read it as a direction)
SELECT met_resolution_sla,
       was_bounced,
       was_reopened,
       COUNT(csat_score)               AS surveys,
       ROUND(AVG(csat_score), 2)       AS avg_csat,
       ROUND(100.0 * AVG((csat_score <= 2)::int), 1) AS pct_unhappy
FROM ticket_facts
WHERE csat_score IS NOT NULL
GROUP BY 1, 2, 3
ORDER BY avg_csat DESC;
