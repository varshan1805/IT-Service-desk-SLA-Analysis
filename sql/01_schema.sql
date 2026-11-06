-- 01_schema.sql
-- Two layers:
--   raw.*    exactly what came out of the ServiceNow-style export, mess included
--   public.* cleaned tables that the analysis and Power BI read from (built in 03_clean.sql)
--
-- Times are IST, stored without a time zone because that's how the export gives them.

DROP SCHEMA IF EXISTS raw CASCADE;
CREATE SCHEMA raw;

CREATE TABLE raw.employees (
    employee_id   TEXT,
    department    TEXT,
    location      TEXT,
    site_type     TEXT
);

CREATE TABLE raw.agents (
    agent_id          TEXT,
    agent_name        TEXT,
    assignment_group  TEXT,
    tier              TEXT,
    joined_on         DATE
);

CREATE TABLE raw.assignment_groups (
    assignment_group  TEXT,
    tier              TEXT,
    shift_pattern     TEXT,
    is_24x7           BOOLEAN,
    headcount         INT
);

CREATE TABLE raw.sla_policy (
    priority                 TEXT,
    response_target_min      INT,
    resolution_target_hours  INT,
    monthly_target_pct       NUMERIC(5,2)
);

-- No primary key on purpose: the export has duplicate rows and I want to
-- see them, not have the load fail on them.
CREATE TABLE raw.tickets (
    ticket_id           TEXT,
    opened_at           TIMESTAMP,
    channel             TEXT,
    requester_id        TEXT,
    category            TEXT,
    subcategory         TEXT,
    priority            TEXT,
    short_description   TEXT,
    status              TEXT,
    assignment_group    TEXT,
    assigned_to         TEXT,
    first_response_at   TIMESTAMP,
    resolved_at         TIMESTAMP,
    closed_at           TIMESTAMP,
    reassignment_count  INT,
    reopen_count        INT,
    work_minutes        INT,
    resolution_code     TEXT,
    csat_score          INT
);

CREATE TABLE raw.ticket_events (
    event_id          BIGINT,
    ticket_id         TEXT,
    event_time        TIMESTAMP,
    event_type        TEXT,
    assignment_group  TEXT,
    agent_id          TEXT
);
