# Power BI dashboard: build notes

The `.pbix` file isn't in this repo yet. These are the notes I build it from, so anyone can rebuild it
and check my DAX. Screenshots go in `/images` once the report is done.

## 1. Connect

There are two ways in. Both give you the same tables.

**Option A, no database needed.** `powerbi/data/` has every `pbi` view already exported as CSV.
Get Data > Text/CSV, load each file, and in Power Query check that the `TRUE`/`FALSE` columns came in as
True/False and the date columns as Date or Date/Time. Rename each query to drop `.csv`.

**Option B, straight from Postgres.** Get Data > PostgreSQL database > server `localhost`, database
`servicedesk`. Import mode is fine for 42k tickets. If you change anything in the SQL, use this option
(or re-export the CSVs).

Only load these tables:

| Table | Grain | Rows (approx.) |
|---|---|---|
| `pbi.fact_ticket` | one row per ticket | 42,300 |
| `pbi.fact_group_time` | one row per stretch of time a ticket sat with a team | 150,000+ |
| `pbi.dim_date` | one row per day, 1 Jan 2025 to 2 Jan 2026 | 367 |
| `pbi.dim_priority` | P1 to P4 with SLA targets | 4 |
| `pbi.dim_group` | assignment groups | 8 |
| `pbi.dim_agent` | agents | 66 |
| `pbi.dim_employee` | requesters | 4,200 |
| `pbi.monthly_sla` | month x priority (for reconciling only, not for visuals) | 48 |

## 2. Model

Star schema, all relationships single direction, one to many:

```
dim_date[date]                 1 ──< fact_ticket[opened_date]
dim_priority[priority]         1 ──< fact_ticket[priority]
dim_group[assignment_group]    1 ──< fact_ticket[resolving_group]
dim_agent[agent_id]            1 ──< fact_ticket[assigned_to]
dim_employee[employee_id]      1 ──< fact_ticket[requester_id]
fact_ticket[ticket_id]         1 ──< fact_group_time[ticket_id]
```

Mark `dim_date` as the date table. Hide every key column on the fact side.
`first_l2_team` and `fact_group_time[assignment_group]` stay as plain columns with no relationship to
`dim_group`, otherwise there are two active paths to the same dimension.

## 3. Measures

Put these in a separate empty table called `_Measures` so they don't get lost among columns.

```dax
Tickets = COUNTROWS ( fact_ticket )

Tickets In SLA Scope =
CALCULATE ( [Tickets], NOT ISBLANK ( fact_ticket[met_resolution_sla] ) )

Breaches =
CALCULATE ( [Tickets], fact_ticket[met_resolution_sla] = FALSE () )

Resolution SLA % =
DIVIDE ( [Tickets In SLA Scope] - [Breaches], [Tickets In SLA Scope] )

Response SLA % =
DIVIDE (
    CALCULATE ( [Tickets], fact_ticket[met_response_sla] = TRUE () ),
    CALCULATE ( [Tickets], NOT ISBLANK ( fact_ticket[met_response_sla] ) )
)

SLA Target % =
DIVIDE ( MAX ( dim_priority[monthly_target_pct] ), 100 )

-- 1 when the priority in context missed its target, 0 otherwise.
-- Only makes sense with one month and one priority in context.
Missed Target =
IF ( [Tickets In SLA Scope] > 0 && [Resolution SLA %] < [SLA Target %], 1, 0 )

-- Credits follow the contract: 2.5% of the 38 lakh fee per missed priority,
-- per month, capped at 10%. ALL(dim_priority) so a priority slicer can't
-- make the credit look smaller than it was.
Service Credit (INR) =
VAR Fee = 3800000
RETURN
    SUMX (
        VALUES ( dim_date[month_start] ),
        VAR MissedThisMonth =
            CALCULATE (
                SUMX ( VALUES ( dim_priority[priority] ), [Missed Target] ),
                ALL ( dim_priority )
            )
        RETURN MIN ( 10, 2.5 * MissedThisMonth ) / 100 * Fee
    )

Breach Rate = DIVIDE ( [Breaches], [Tickets In SLA Scope] )

Bounced Tickets =
CALCULATE ( [Tickets], fact_ticket[was_bounced] = TRUE () )

Bounce Rate = DIVIDE ( [Bounced Tickets], [Tickets] )

Share Of Breaches From Bounces =
DIVIDE (
    CALCULATE ( [Breaches], fact_ticket[was_bounced] = TRUE () ),
    [Breaches]
)

Resolved Tickets =
CALCULATE ( [Tickets], NOT ISBLANK ( fact_ticket[resolution_hours] ) )

Reopen Rate =
DIVIDE ( CALCULATE ( [Resolved Tickets], fact_ticket[was_reopened] = TRUE () ), [Resolved Tickets] )

Median Resolution Hours = MEDIAN ( fact_ticket[resolution_hours] )

Median Response Minutes = MEDIAN ( fact_ticket[response_minutes] )

Avg CSAT = AVERAGE ( fact_ticket[csat_score] )

CSAT Responses = COUNT ( fact_ticket[csat_score] )

Hours In Wrong Queue =
CALCULATE ( SUM ( fact_group_time[hours] ), fact_group_time[is_wrong_team] = TRUE () )

After Hours Share =
DIVIDE ( CALCULATE ( [Tickets], fact_ticket[opened_after_hours] = TRUE () ), [Tickets] )

Tickets Per Day =
DIVIDE ( [Tickets], DISTINCTCOUNT ( dim_date[date] ) )
```

### Checking the DAX against SQL

Before trusting any visual, build a table with `dim_date[month_start]`, `dim_priority[priority]`,
`[Resolution SLA %]` and `[Missed Target]`, and compare it with `pbi.monthly_sla`. They should match to the
second decimal. `[Service Credit (INR)]` for the full year should be **29,45,000**. If it isn't, the measure
or a relationship is wrong.

One known limit: slicers on anything other than date or priority (site type, team) still change
`[Service Credit (INR)]`, because they change which tickets count. Credits are a contract-level number,
so I only show that card on page 1 where those slicers aren't present.

## 4. Pages

**Page 1, Contract health** (for the account manager)
- Cards: Service Credit (INR), Resolution SLA %, Response SLA %, Breaches
- Line chart: Resolution SLA % by month, small multiples by priority, with SLA Target % as a constant line
- Column chart: Service Credit (INR) by month
- Slicer: month range only

**Page 2, Why tickets breach** (for the service delivery manager)
- Bar: Breach Rate by `bounces` (0, 1, 2+)
- Matrix: rows `subcategory`, columns `first_l2_team`, values Bounced Tickets, filtered to bounced tickets.
  Conditional formatting on the values so the big misroute paths stand out
- Bar: Hours In Wrong Queue by `fact_group_time[assignment_group]`
- Card: Share Of Breaches From Bounces

**Page 3, When tickets arrive**
- Line: Response SLA % by `opened_hour`, legend `site_type` (Office and Warehouse only)
- Matrix heatmap: rows `dim_date[weekday_name]` (sorted by `weekday_no`), columns `opened_hour`,
  values Tickets Per Day, background colour scale
- Column: Tickets by `dim_date[date]` day number for ERP subcategories (month-end spike)

**Page 4, Team quality**
- Bar: Reopen Rate by `resolving_group`
- Table: `dim_agent[agent_name]`, Resolved Tickets, Reopen Rate, Avg CSAT, filtered to one team via slicer
- Scatter: Reopen Rate vs Avg CSAT by team

**Page 5, VPN incident**
- Line: Tickets by `dim_date[week_start]`, filtered to subcategory VPN, May to October
- Line: Breach Rate by week for Network Operations
- Text box with the dates of the v5.2 rollout and the hotfix

## 5. Design rules I'm following

- One accent colour for "bad" (missed, bounced, reopened), everything else in one neutral blue
- No pie charts, no 3D, no gauges
- Page titles state the finding, e.g. "Wrong first stop = 4x the breach rate" instead of
  "Breach rate by bounce count"
