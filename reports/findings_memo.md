# Service desk SLA review, 2025

**To:** Service Delivery Manager, Tidewater Logistics account
**From:** Varshan Raj
**Data:** 42,285 tickets, 1 Jan to 31 Dec 2025 (simulated, see README)

## The short version

We paid **₹29.45 lakh in service credits in 2025**, about 6.5% of the year's fee. Two process changes
would have cut that to about ₹13.3 lakh. Neither needs new headcount.

1. Ask the user to confirm the fix before resolving a ticket. On P1 and P2 this is the whole game: a reopened
   P1 or P2 breaches 98% of the time, and reopens are behind 76% of all P2 breaches.
2. Fix routing for about ten "grey area" ticket types that L1 keeps sending to the wrong team.

P1 will still miss its target after both changes. That needs a separate look (section 4).

## 1. Where the money went

| Priority | Months missed | Average compliance | Target |
|---|---|---|---|
| P1 | 12 of 12 | 87.8% | 95% |
| P2 | 11 of 12 | 93.2% | 95% |
| P3 | 8 of 12 | 89.4% | 90% |
| P4 | 0 of 12 | 95.1% | 90% |

P3 sits right on its line, so small gains there turn straight into money. P1 and P2 miss nearly every month.

## 2. What's causing the breaches

**Tickets sent to the wrong team first.** 11.8% of tickets went to at least one wrong L2 team before reaching
the right one. Those tickets produced 41.5% of all breaches.

| Route | Breach rate |
|---|---|
| Straight to the right team | 5.6% |
| One wrong team first | 23.1% |
| Two or more wrong teams | 45.6% |

This holds after controlling for priority, ticket type, resolving team and time of day: a bounce still
multiplies the odds of a breach by about 10. The time lost is almost all queue time. Bounced tickets spent
an average of 34 hours sitting with teams that weren't going to fix them, 166,500 ticket-hours in total.

The worst paths: Wi-Fi tickets sent to Desktop Support instead of Network Ops, warehouse scanner tickets sent
to Desktop Support or Network Ops instead of Warehouse Systems, and "Something not working" tickets, which end up in
one of three wrong teams before Desktop Support gets them.

**Reopens.** Desktop Support reopens 13.6% of its tickets against 4.1% across the other teams. The rate is
flat across all nine engineers (11.2% to 14.7%, no statistically significant difference), so the cause is
how the team closes tickets. Across all teams, a reopen raises the odds of a breach about 40 times,
because the SLA clock runs to the final fix.

**The night gap.** L1 works 08:00 to 20:00 on weekdays. The warehouses don't stop. 64% of warehouse tickets
come in while L1 is closed, and only 33.8% of those get a first response inside SLA (92.8% during L1 hours).
Most of the damage is to the response SLA, which carries no credits, so this is a smaller money problem.
It is a real problem for the client, though. There were 1,416 warehouse lockouts and password resets raised at
night, and they waited a median of 9.6 hours for a 10-minute fix.

**Two events worth remembering.**
- The VPN client v5.2 rollout (14 Jul to 25 Aug) roughly tripled VPN tickets and added about 390 tickets.
  It also slowed everything else Network Ops owned: their non-VPN breach rate went from 7.8% to 10.2% during
  those six weeks.
- ERP tickets run 2.2 times higher from the 28th to the 2nd of each month (finance month-end close).

## 3. What to do, and what it's worth

I re-scored every month of 2025 under each change, assuming each one removes **half** of the problem, not all of it.

| Change | Credits in 2025 | Saving |
|---|---|---|
| As it was | ₹29.45 lakh | |
| Fix routing only | ₹25.65 lakh | ₹3.80 lakh |
| Confirm before closing only | ₹15.20 lakh | ₹14.25 lakh |
| Both | ₹13.30 lakh | ₹16.15 lakh |

**1. Confirm before closing** (biggest saving, start here)
Before resolving, the engineer gets a "yes, it works" from the user by call or chat. Mandatory on P1 and P2,
and on all Desktop Support tickets. Track reopen rate weekly per team. Desktop Support's target is the other
teams' level, around 5%.

**2. Fix routing for the grey-area ticket types**
Give L1 a one-page routing guide for the ten ticket types that bounce most (Wi-Fi, WMS scanner, WMS error,
label printer, ERP error, ERP performance, VPN, slow network, new access request, "something not working").
Replace the free-text "Something not working" option on the portal with three or four guided questions.
Review the top misroute paths every month.

**3. Self-service password reset**
Resets and lockouts are 18.2% of all tickets. At 70% adoption this saves about 1,050 L1 hours a year
(about half a person, ₹4.4 lakh). The bigger reason is the warehouse night shift: it would remove up to
13,700 hours of locked-out staff waiting, worth up to ₹15 lakh to the client. That figure is an upper bound,
since supervisors usually move people to other work. One caution: warehouse staff need a registered phone or
another way to verify themselves, and I don't know how many have one.

**4. Small fixes that cost nothing**
- Keep ERP Application Support leave and training away from the 28th to the 2nd.
- Put software updates that touch every laptop through a pilot group first. The VPN rollout is the example.
- Laptop issues are the single biggest source of breaches (15% of them). The ticket data doesn't say why.
  If most of those were waiting on parts, a small pool of spare laptops to swap would fix it. Worth checking
  with Desktop Support.

**5. Night cover at L1: not yet**
One L1 seat from 20:00 to 08:00 every night costs about ₹21 lakh a year. Most of what it fixes is response
time, which carries no credits under this contract. I haven't modelled its effect on resolution credits, but I
don't expect it to come close to the seat's cost. There are about 25 after-hours tickets a night. Do
self-service reset first, then see what's left.

## 4. What this doesn't fix

**P1 will keep missing.** In every scenario P1 still fails all 12 months. Even P1 tickets that went straight
to the right team and were never reopened breach 6.3% of the time, and with about 50 P1s a month the 95%
target only allows two breaches. The largest group of P1s is site outages (37%). The next step is to go through those tickets with
Network Ops and find out how many were waiting on the telecom carrier. If most were, the options are a
back-to-back SLA with the carrier, a backup link at the warehouses, or renegotiating how carrier-caused
outages are counted. The ticket data can't answer that on its own.

## Caveats

- The data is simulated. The patterns are realistic, but the numbers are not from a real client.
- Savings assume each change removes half of the problem. They are estimates of direction and size, not promises.
- CSAT comes from about 21% of resolved tickets, so I've used it only as a direction.
- The monitoring integration logged resolution times in UTC from 1 Mar to 15 Apr. I corrected 538 tickets
  using the audit log before any of this analysis.
