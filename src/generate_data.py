"""
Builds a year of IT service desk data for a fictional company,
Tidewater Logistics (about 4,200 employees, offices plus 24x7 warehouses).

The IT support is outsourced to a managed service provider. The provider is
paid a monthly fee and has to give money back (service credits) whenever it
misses an SLA target. That's the business problem the analysis looks at.

The data is simulated. I built it from how service desks actually behave,
so the patterns in it are deliberate:
  - tickets that get routed to the wrong team wait much longer
  - L1 isn't staffed at night, but the warehouses work through the night
  - Monday mornings pile up
  - ERP tickets spike around month end
  - a bad VPN client update in July caused a six-week flood of tickets
  - Desktop Support closes tickets fast and a lot of them come back
  - a monitoring integration wrote times in UTC for six weeks (data bug)

Run:  python src/generate_data.py
Output goes to data/raw/ as CSV files.
"""

import csv
from datetime import datetime, timedelta

import numpy as np

import settings as cfg

rng = np.random.default_rng(cfg.SEED)


# ---------------------------------------------------------------------------
# Calendar and shift helpers
# ---------------------------------------------------------------------------

HOLIDAYS_2025 = {
    datetime(2025, 1, 1).date(), datetime(2025, 1, 14).date(), datetime(2025, 1, 15).date(),
    datetime(2025, 1, 26).date(), datetime(2025, 3, 31).date(), datetime(2025, 4, 14).date(),
    datetime(2025, 4, 18).date(), datetime(2025, 5, 1).date(), datetime(2025, 8, 15).date(),
    datetime(2025, 8, 27).date(), datetime(2025, 10, 1).date(), datetime(2025, 10, 2).date(),
    datetime(2025, 10, 20).date(), datetime(2025, 12, 25).date(),
}

# Shift windows per weekday (Mon=0). None means the team is off that day.
# "24x7" teams are always on.
WEEKDAY_8_TO_8 = {0: (8, 20), 1: (8, 20), 2: (8, 20), 3: (8, 20), 4: (8, 20), 5: (9, 14), 6: None}
MON_SAT_9_TO_6 = {0: (9, 18), 1: (9, 18), 2: (9, 18), 3: (9, 18), 4: (9, 18), 5: (9, 18), 6: None}
MON_FRI_9_TO_7 = {0: (9, 19), 1: (9, 19), 2: (9, 19), 3: (9, 19), 4: (9, 19), 5: None, 6: None}
MON_FRI_9_TO_6 = {0: (9, 18), 1: (9, 18), 2: (9, 18), 3: (9, 18), 4: (9, 18), 5: None, 6: None}
DAILY_6_TO_10 = {d: (6, 22) for d in range(7)}

GROUPS = {
    # name: (tier, schedule or "24x7", headcount)
    "Service Desk L1":          ("L1", WEEKDAY_8_TO_8, 22),
    "Desktop Support":          ("L2", MON_SAT_9_TO_6, 9),
    "Network Operations":       ("L2", "24x7", 7),
    "Server & Cloud Ops":       ("L2", "24x7", 8),
    "ERP Application Support":  ("L2", MON_FRI_9_TO_7, 6),
    "Collaboration Support":    ("L2", MON_FRI_9_TO_6, 4),
    "Identity & Access":        ("L2", MON_FRI_9_TO_6, 4),
    "Warehouse Systems":        ("L2", DAILY_6_TO_10, 6),
}

SHIFT_LABELS = {
    "Service Desk L1": "Mon-Fri 08:00-20:00, Sat 09:00-14:00",
    "Desktop Support": "Mon-Sat 09:00-18:00",
    "Network Operations": "24x7",
    "Server & Cloud Ops": "24x7",
    "ERP Application Support": "Mon-Fri 09:00-19:00",
    "Collaboration Support": "Mon-Fri 09:00-18:00",
    "Identity & Access": "Mon-Fri 09:00-18:00",
    "Warehouse Systems": "Daily 06:00-22:00",
}


def shift_window(schedule, day):
    """Return (start, end) datetimes of the shift on this date, or None."""
    if schedule == "24x7":
        start = datetime(day.year, day.month, day.day)
        return start, start + timedelta(days=1)
    if day in HOLIDAYS_2025:
        # On public holidays L1 runs its Saturday hours, everyone else is off
        hours = schedule.get(5) if schedule is WEEKDAY_8_TO_8 else None
        if schedule is DAILY_6_TO_10:
            hours = schedule[day.weekday()]
    else:
        hours = schedule.get(day.weekday())
    if hours is None:
        return None
    start = datetime(day.year, day.month, day.day, hours[0])
    end = datetime(day.year, day.month, day.day, hours[1])
    return start, end


def add_working_minutes(t, minutes, schedule):
    """Move forward `minutes` of on-shift time from t. Off-shift time doesn't count."""
    if schedule == "24x7":
        return t + timedelta(minutes=minutes)
    remaining = minutes
    day = t.date()
    for _ in range(60):  # never needs more than a couple of weeks
        window = shift_window(schedule, day)
        if window:
            start, end = window
            if t < start:
                t = start
            if t < end:
                available = (end - t).total_seconds() / 60
                if remaining <= available:
                    return t + timedelta(minutes=remaining)
                remaining -= available
        day = day + timedelta(days=1)
        t = datetime(day.year, day.month, day.day)
    raise RuntimeError("couldn't find a shift window, check the schedules")


def group_schedule(group, priority):
    """P1/P2 get the on-call engineer after hours, so the clock never stops for them."""
    if priority in ("P1", "P2"):
        return "24x7"
    return GROUPS[group][1]


def lognormal_minutes(median, spread=0.6):
    return float(rng.lognormal(np.log(median), spread))


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------

FIRST_NAMES = [
    "Arun", "Priya", "Karthik", "Divya", "Suresh", "Lakshmi", "Vignesh", "Anitha",
    "Rahul", "Sneha", "Pradeep", "Kavya", "Manoj", "Deepa", "Sanjay", "Meena",
    "Ashwin", "Nandhini", "Rohit", "Pooja", "Gokul", "Swathi", "Naveen", "Revathi",
    "Harish", "Ishaan", "Farhan", "Sowmya", "Ajay", "Bhavana", "Dinesh", "Gayathri",
    "Imran", "Janani", "Kiran", "Monica", "Nikhil", "Pavithra", "Ramesh", "Shalini",
]
LAST_NAMES = [
    "Kumar", "Ramesh", "Iyer", "Nair", "Reddy", "Sharma", "Krishnan", "Subramanian",
    "Patel", "Menon", "Rao", "Shetty", "Joseph", "Gupta", "Pillai", "Das", "Khan",
    "Verma", "Naidu", "Raghavan",
]

LOCATIONS = [
    # name, site type, share of employees
    ("Chennai HQ", "Office", 0.22),
    ("Bengaluru Office", "Office", 0.13),
    ("Pune Office", "Office", 0.10),
    ("Gurugram Office", "Office", 0.11),
    ("Sriperumbudur Warehouse", "Warehouse", 0.14),
    ("Hosur Warehouse", "Warehouse", 0.10),
    ("Bhiwandi Warehouse", "Warehouse", 0.12),
    ("Manesar Warehouse", "Warehouse", 0.08),
]

OFFICE_DEPTS = ["Finance", "HR", "Sales", "Customer Service", "Procurement",
                "Operations Planning", "IT", "Leadership", "Legal"]
OFFICE_DEPT_WEIGHTS = [0.14, 0.07, 0.20, 0.22, 0.08, 0.14, 0.06, 0.03, 0.06]


def build_employees(n=4200):
    names = [l[0] for l in LOCATIONS]
    shares = np.array([l[2] for l in LOCATIONS])
    site_type = {l[0]: l[1] for l in LOCATIONS}
    employees = []
    for i in range(n):
        loc = rng.choice(names, p=shares / shares.sum())
        if site_type[loc] == "Warehouse":
            dept = "Warehouse Operations"
        else:
            dept = rng.choice(OFFICE_DEPTS, p=OFFICE_DEPT_WEIGHTS)
        employees.append({
            "employee_id": f"EMP{10001 + i}",
            "department": dept,
            "location": loc,
            "site_type": site_type[loc],
        })
    return employees


def build_agents():
    agents = []
    used = set()
    n = 1
    for group, (tier, _, headcount) in GROUPS.items():
        for _ in range(headcount):
            while True:
                name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
                if name not in used:
                    used.add(name)
                    break
            joined = datetime(2019, 1, 1) + timedelta(days=int(rng.integers(0, 6 * 365)))
            agents.append({
                "agent_id": f"AG{n:03d}",
                "agent_name": name,
                "assignment_group": group,
                "tier": tier,
                "joined_on": joined.date().isoformat(),
            })
            n += 1
    return agents


# ---------------------------------------------------------------------------
# What kinds of tickets come in
# ---------------------------------------------------------------------------

# subcategory -> (category, resolving group, median work minutes, can L1 fix it)
SUBCATEGORIES = {
    "Password reset":        ("Access & Identity", "Service Desk L1", 9, True),
    "Account lockout":       ("Access & Identity", "Service Desk L1", 11, True),
    "MFA issue":             ("Access & Identity", "Identity & Access", 25, True),
    "New access request":    ("Access & Identity", "Identity & Access", 150, False),
    "Outlook issue":         ("Email & Collaboration", "Collaboration Support", 35, True),
    "Teams issue":           ("Email & Collaboration", "Collaboration Support", 30, True),
    "Shared mailbox":        ("Email & Collaboration", "Collaboration Support", 40, False),
    "Laptop issue":          ("Hardware", "Desktop Support", 120, False),
    "Printer issue":         ("Hardware", "Desktop Support", 50, False),
    "Label printer":         ("Hardware", "Desktop Support", 45, False),
    "Peripheral":            ("Hardware", "Desktop Support", 30, True),
    "VPN":                   ("Network", "Network Operations", 45, False),
    "Wi-Fi":                 ("Network", "Network Operations", 60, False),
    "Slow network":          ("Network", "Network Operations", 110, False),
    "Site down":             ("Network", "Network Operations", 100, False),
    "ERP error":             ("Business Applications", "ERP Application Support", 140, False),
    "ERP performance":       ("Business Applications", "ERP Application Support", 160, False),
    "HR portal":             ("Business Applications", "ERP Application Support", 60, False),
    "WMS scanner":           ("Business Applications", "Warehouse Systems", 50, False),
    "WMS error":             ("Business Applications", "Warehouse Systems", 90, False),
    "Software install":      ("Software", "Desktop Support", 40, True),
    "License request":       ("Software", "Desktop Support", 60, False),
    "OS update":             ("Software", "Desktop Support", 45, True),
    "VM down":               ("Server & Cloud", "Server & Cloud Ops", 80, False),
    "Disk space alert":      ("Server & Cloud", "Server & Cloud Ops", 35, False),
    "Backup failure":        ("Server & Cloud", "Server & Cloud Ops", 110, False),
    "High CPU / memory":     ("Server & Cloud", "Server & Cloud Ops", 70, False),
    "General query":         ("Other", "Service Desk L1", 20, True),
    "Something not working": ("Other", "Desktop Support", 70, False),
}

OFFICE_MIX = {
    "Password reset": 14, "Account lockout": 7, "MFA issue": 4, "New access request": 6,
    "Outlook issue": 7, "Teams issue": 5, "Shared mailbox": 2, "Laptop issue": 9,
    "Printer issue": 4, "Peripheral": 3, "VPN": 7, "Wi-Fi": 3, "Slow network": 3,
    "ERP error": 5, "ERP performance": 2, "HR portal": 2, "Software install": 6,
    "License request": 2, "OS update": 2, "General query": 3, "Something not working": 4,
}
WAREHOUSE_MIX = {
    "WMS scanner": 22, "WMS error": 14, "Label printer": 16, "Wi-Fi": 14,
    "Password reset": 12, "Account lockout": 8, "Laptop issue": 4, "Peripheral": 4,
    "Something not working": 6,
}
MONITORING_MIX = {
    "Disk space alert": 35, "Backup failure": 22, "High CPU / memory": 25,
    "VM down": 8, "Site down": 10,
}

PRIORITY_MIX = {
    "Site down":         [0.55, 0.45, 0.00, 0.00],
    "VM down":           [0.35, 0.50, 0.15, 0.00],
    "WMS error":         [0.05, 0.25, 0.60, 0.10],
    "WMS scanner":       [0.00, 0.08, 0.72, 0.20],
    "Backup failure":    [0.00, 0.15, 0.75, 0.10],
    "Disk space alert":  [0.02, 0.18, 0.60, 0.20],
    "High CPU / memory": [0.03, 0.17, 0.60, 0.20],
    "ERP error":         [0.02, 0.12, 0.66, 0.20],
    "ERP performance":   [0.02, 0.15, 0.63, 0.20],
    "Password reset":    [0.00, 0.03, 0.77, 0.20],
    "Account lockout":   [0.00, 0.05, 0.75, 0.20],
    "New access request": [0.00, 0.00, 0.30, 0.70],
    "Software install":  [0.00, 0.00, 0.30, 0.70],
    "License request":   [0.00, 0.00, 0.30, 0.70],
    "_default":          [0.003, 0.04, 0.55, 0.407],
}

# How often L1 sends a ticket to the wrong team, and where it ends up.
# These are the "grey area" tickets: is a slow ERP screen an app problem,
# a server problem or a network problem? L1 guesses.
MISROUTE = {
    "Slow network":          (0.38, ["Server & Cloud Ops", "Desktop Support"]),
    "ERP performance":       (0.42, ["Server & Cloud Ops", "Network Operations"]),
    "WMS scanner":           (0.30, ["Desktop Support", "Network Operations"]),
    "WMS error":             (0.22, ["ERP Application Support", "Server & Cloud Ops"]),
    "Wi-Fi":                 (0.20, ["Desktop Support"]),
    "VPN":                   (0.16, ["Desktop Support", "Identity & Access"]),
    "Something not working": (0.55, ["Network Operations", "Collaboration Support", "ERP Application Support"]),
    "New access request":    (0.18, ["ERP Application Support", "Collaboration Support"]),
    "ERP error":             (0.12, ["Server & Cloud Ops"]),
    "HR portal":             (0.15, ["Identity & Access"]),
    "Label printer":         (0.20, ["Warehouse Systems"]),
    "Shared mailbox":        (0.12, ["Identity & Access"]),
    "MFA issue":             (0.10, ["Collaboration Support"]),
}
DEFAULT_MISROUTE = 0.05

L1_FIX_RATE = {
    "Password reset": 0.97, "Account lockout": 0.95, "General query": 0.90,
    "Outlook issue": 0.45, "Teams issue": 0.50, "MFA issue": 0.40,
    "Peripheral": 0.35, "Software install": 0.30, "OS update": 0.35,
}

PICKUP_MEDIAN_MIN = {"P1": 4, "P2": 9, "P3": 30, "P4": 60}
L2_PICKUP_MEDIAN_MIN = {"P1": 8, "P2": 20, "P3": 120, "P4": 300}

DESCRIPTIONS = {
    "Password reset": ["Forgot my password", "Password expired, can't log in", "Need password reset for laptop login"],
    "Account lockout": ["Account locked after wrong password", "Locked out of my account", "AD account locked again"],
    "MFA issue": ["Not getting the MFA prompt on phone", "Changed phone, need MFA re-registered", "Authenticator code not accepted"],
    "New access request": ["Need access to Finance shared drive", "New joiner needs ERP access", "Requesting access to sales dashboard"],
    "Outlook issue": ["Outlook not syncing", "Outlook keeps asking for password", "Emails stuck in outbox"],
    "Teams issue": ["Teams calls dropping", "Can't share screen on Teams", "Teams not opening"],
    "Shared mailbox": ["Add me to the accounts payable mailbox", "Shared mailbox not showing in Outlook"],
    "Laptop issue": ["Laptop very slow", "Laptop not turning on", "Screen flickering", "Battery drains in an hour", "Keyboard not working"],
    "Printer issue": ["Printer on 3rd floor not printing", "Print jobs stuck in queue", "Scanner to email not working"],
    "Label printer": ["Label printer at dock 4 printing blank labels", "Zebra printer offline", "Labels coming out misaligned"],
    "Peripheral": ["Need a new mouse", "Docking station not detecting monitor", "Headset mic not working"],
    "VPN": ["VPN not connecting from home", "VPN keeps disconnecting", "VPN connected but can't open ERP"],
    "Wi-Fi": ["Wi-Fi dropping in the warehouse", "Can't connect to office Wi-Fi", "Very weak Wi-Fi near loading bay"],
    "Slow network": ["Everything is slow today", "Network very slow on 2nd floor", "Files taking ages to open from shared drive"],
    "Site down": ["Whole site has no network", "Internet down at the warehouse", "Branch link down"],
    "ERP error": ["Error while posting invoice", "Can't generate GRN in ERP", "ERP throwing error on month end report"],
    "ERP performance": ["ERP is very slow", "ERP report timing out", "ERP screens freezing"],
    "HR portal": ["Can't apply leave on HR portal", "Payslip not loading", "HR portal login error"],
    "WMS scanner": ["Scanner not syncing with WMS", "Handheld scanner frozen", "Scanner shows wrong bin location"],
    "WMS error": ["WMS not allocating pick lists", "Dispatch screen stuck in WMS", "Inventory count mismatch in WMS"],
    "Software install": ["Need Power BI Desktop installed", "Install Zoom please", "Need Python on my laptop"],
    "License request": ["Need Adobe Acrobat Pro license", "Visio license request", "Office license expired"],
    "OS update": ["Windows update stuck at 30%", "Laptop asking to restart for update every day"],
    "VM down": ["[ALERT] VM unreachable", "[ALERT] Host not responding to ping"],
    "Disk space alert": ["[ALERT] Disk C: above 90%", "[ALERT] /var above 85% used", "[ALERT] Low disk space on DB server"],
    "Backup failure": ["[ALERT] Nightly backup job failed", "[ALERT] Backup completed with errors"],
    "High CPU / memory": ["[ALERT] CPU above 95% for 15 min", "[ALERT] Memory usage critical"],
    "General query": ["How do I set up email on my phone?", "Who do I contact for ID card?", "Where do I raise a new laptop request?"],
    "Something not working": ["Not working", "System issue please check urgent", "Unable to work, please help", "Error coming"],
}


# ---------------------------------------------------------------------------
# Ticket arrivals
# ---------------------------------------------------------------------------

def office_hour_weights():
    w = np.array([0.2, 0.1, 0.1, 0.1, 0.1, 0.2, 0.4, 1.0, 3.0, 9.0, 11.0, 10.0,
                  7.0, 6.0, 8.0, 8.0, 7.0, 5.0, 3.0, 2.0, 1.4, 1.0, 0.6, 0.3])
    return w / w.sum()


def warehouse_hour_weights():
    # Three shifts. Spikes at shift change (06, 14, 22) when people log in.
    w = np.full(24, 3.0)
    for h in (6, 14, 22):
        w[h] = 7.0
        w[(h + 1) % 24] = 5.0
    return w / w.sum()


def arrival_times(day):
    """Yield (timestamp, source) for every ticket opened on this date."""
    dow = day.weekday()
    holiday = day in HOLIDAYS_2025

    office = 100.0
    if dow == 0:
        office *= 1.30
    elif dow == 4:
        office *= 0.92
    elif dow == 5:
        office = 15.0
    elif dow == 6:
        office = 5.0
    if holiday:
        office *= 0.2

    warehouse = 30.0 * (0.85 if dow == 6 else 1.0)
    monitoring = 12.0

    base = datetime(day.year, day.month, day.day)
    for source, mean, weights in (
        ("office", office, office_hour_weights()),
        ("warehouse", warehouse, warehouse_hour_weights()),
        ("monitoring", monitoring, np.full(24, 1 / 24)),
    ):
        n = rng.poisson(mean)
        hours = rng.choice(24, size=n, p=weights)
        for h in hours:
            yield base + timedelta(hours=int(h), seconds=int(rng.integers(0, 3600))), source


def pick_subcategory(source, t):
    mix = {"office": OFFICE_MIX, "warehouse": WAREHOUSE_MIX, "monitoring": MONITORING_MIX}[source]
    mix = dict(mix)
    if "ERP error" in mix and (t.day >= 28 or t.day <= 2):
        mix["ERP error"] *= 3.0
        mix["ERP performance"] *= 3.0
    if "VPN" in mix and cfg.VPN_INCIDENT_START <= t < cfg.VPN_INCIDENT_END:
        mix["VPN"] *= 3.5
    names = list(mix)
    p = np.array([mix[k] for k in names], dtype=float)
    return rng.choice(names, p=p / p.sum())


def pick_priority(subcat, t):
    p = list(PRIORITY_MIX.get(subcat, PRIORITY_MIX["_default"]))
    if subcat.startswith("ERP") and (t.day >= 28 or t.day <= 2):
        p = [p[0], p[1] + 0.10, p[2] - 0.10, p[3]]  # finance shouts louder at month end
    return rng.choice(["P1", "P2", "P3", "P4"], p=np.array(p) / sum(p))


# ---------------------------------------------------------------------------
# Life of a ticket
# ---------------------------------------------------------------------------

class TicketBuilder:
    def __init__(self, employees, agents):
        self.office_staff = [e for e in employees if e["site_type"] == "Office"]
        self.warehouse_staff = [e for e in employees if e["site_type"] == "Warehouse"]
        self.agents_by_group = {}
        for a in agents:
            self.agents_by_group.setdefault(a["assignment_group"], []).append(a["agent_id"])
        self.tickets = []
        self.events = []
        self.event_seq = 1

    def agent(self, group):
        return str(rng.choice(self.agents_by_group[group]))

    def log(self, ticket_id, when, event_type, group, agent=None):
        self.events.append({
            "event_id": self.event_seq,
            "ticket_id": ticket_id,
            "event_time": when,
            "event_type": event_type,
            "assignment_group": group,
            "agent_id": agent,
        })
        self.event_seq += 1

    def pickup_wait(self, priority, when, l2=False, group=None, wrong_queue=False):
        median = (L2_PICKUP_MEDIAN_MIN if l2 else PICKUP_MEDIAN_MIN)[priority]
        # Monday morning queue: weekend tickets plus the Monday rush
        if when.weekday() == 0 and when.hour < 13:
            median *= 1.8
        # A ticket in the wrong queue sits there. Nobody is in a hurry to
        # pick up something that "isn't ours".
        if wrong_queue:
            median *= 2.5
        # During the VPN mess Network Ops was buried, so everything they
        # owned waited longer, VPN or otherwise
        if group == "Network Operations" and cfg.VPN_INCIDENT_START <= when < cfg.VPN_INCIDENT_END:
            median *= 3.0
        return lognormal_minutes(median, 0.7)

    def build(self, ticket_no, opened, source):
        tid = f"INC{ticket_no:07d}"
        self.first_event = len(self.events)
        subcat = pick_subcategory(source, opened)
        category, right_group, work_median, l1_can_fix = SUBCATEGORIES[subcat]
        priority = pick_priority(subcat, opened)
        requester = rng.choice(self.warehouse_staff if source == "warehouse" else self.office_staff)
        channel = "Monitoring" if source == "monitoring" else rng.choice(
            ["Portal", "Email", "Phone", "Chat"], p=[0.45, 0.25, 0.20, 0.10])
        if source == "warehouse":
            channel = rng.choice(["Phone", "Portal", "Chat"], p=[0.55, 0.30, 0.15])

        ticket = {
            "ticket_id": tid,
            "opened_at": opened,
            "channel": channel,
            "requester_id": requester["employee_id"] if source != "monitoring" else None,
            "category": category,
            "subcategory": subcat,
            "priority": priority,
            "short_description": rng.choice(DESCRIPTIONS[subcat]),
        }

        # About 2.5% get cancelled: duplicates, or the user sorts it out first
        if rng.random() < 0.025 and source != "monitoring":
            return self.cancel(ticket, opened)

        in_vpn_incident = subcat == "VPN" and cfg.VPN_INCIDENT_START <= opened < cfg.VPN_INCIDENT_END
        work_minutes = 0.0
        groups_visited = []

        # --- First touch -------------------------------------------------
        # Monitoring alerts skip L1 and land straight in an L2 queue (below).
        # Everything else is picked up by L1 first.
        first_response = None
        if source == "monitoring":
            t = opened
            current = None
        else:
            entry_group = "Service Desk L1"
            self.log(tid, opened, "Created", entry_group)
            sched = group_schedule(entry_group, priority)
            t = add_working_minutes(opened, self.pickup_wait(priority, opened), sched)
            first_response = t
            l1_agent = self.agent(entry_group)
            self.log(tid, t, "Assigned", entry_group, l1_agent)
            groups_visited.append(entry_group)

            l1_fixed = l1_can_fix and rng.random() < L1_FIX_RATE.get(subcat, 0)
            if right_group == "Service Desk L1" and not l1_fixed:
                # L1-owned but needed a second look; L1 still owns it
                l1_fixed = True
                work_median *= 2.5
            if l1_fixed:
                minutes = lognormal_minutes(work_median, 0.5)
                work_minutes += minutes
                t = add_working_minutes(t, minutes, sched)
                return self.finish(ticket, t, first_response, entry_group, l1_agent,
                                   groups_visited, work_minutes, in_vpn_incident, l2=False)

            triage = lognormal_minutes(7, 0.4)
            work_minutes += triage
            t = add_working_minutes(t, triage, sched)
            current = None

        # --- Routing, possibly to the wrong team first -------------------
        misroute_p, wrong_options = MISROUTE.get(subcat, (DEFAULT_MISROUTE, None))
        if wrong_options is None:
            wrong_options = [g for g in GROUPS if g not in (right_group, "Service Desk L1")]

        hops = 0
        target = right_group
        if rng.random() < misroute_p:
            target = rng.choice([g for g in wrong_options if g != right_group])
            hops = 1
            if rng.random() < 0.28:
                hops = 2

        if source == "monitoring":
            # The alert rules decide the queue, and they're mostly right
            self.log(tid, opened, "Created", target)
            current = target

        while True:
            if current != target:
                self.log(tid, t, "Reassigned", target)
                current = target
            sched = group_schedule(current, priority)
            wait = self.pickup_wait(priority, t,
                                    l2=source != "monitoring" or bool(groups_visited),
                                    group=current, wrong_queue=current != right_group)
            t = add_working_minutes(t, wait, sched)
            agent = self.agent(current)
            self.log(tid, t, "Assigned", current, agent)
            groups_visited.append(current)
            if first_response is None:
                first_response = t

            if current == right_group:
                break

            # Wrong team: someone reads it, maybe pokes at it, then bounces it
            look = lognormal_minutes(18, 0.5)
            work_minutes += look
            t = add_working_minutes(t, look, sched)
            hops -= 1
            if hops > 0:
                options = [g for g in GROUPS if g not in (right_group, current, "Service Desk L1")]
                target = rng.choice(options)
            else:
                target = right_group

        # --- Real work in the right team ---------------------------------
        median = work_median
        if current == "Desktop Support":
            median *= 0.8      # they close fast...
        if in_vpn_incident:
            median *= 1.6      # no proper fix until the hotfix
        minutes = lognormal_minutes(median, 0.6)
        work_minutes += minutes
        t = add_working_minutes(t, minutes, sched)

        # Waiting on parts or on the user. The clock keeps running (calendar SLA).
        if subcat == "Laptop issue" and rng.random() < 0.18:
            t += timedelta(hours=float(rng.uniform(24, 96)))
        elif priority in ("P3", "P4") and rng.random() < 0.15:
            t += timedelta(hours=float(rng.uniform(3, 30)))

        return self.finish(ticket, t, first_response, current, agent,
                           groups_visited, work_minutes, in_vpn_incident, l2=True)

    def finish(self, ticket, resolved, first_response, group, agent,
               groups_visited, work_minutes, in_vpn_incident, l2):
        tid = ticket["ticket_id"]
        priority = ticket["priority"]
        self.log(tid, resolved, "Resolved", group, agent)
        reopen_count = 0

        reopen_p = 0.14 if group == "Desktop Support" else 0.04
        if in_vpn_incident:
            reopen_p = 0.22
        if rng.random() < reopen_p:
            reopen_count = 1
            reopened = resolved + timedelta(hours=float(rng.uniform(3, 60)))
            self.log(tid, reopened, "Reopened", group)
            sched = group_schedule(group, priority)
            t = add_working_minutes(reopened, self.pickup_wait(priority, reopened, l2=l2, group=group), sched)
            extra = lognormal_minutes(SUBCATEGORIES[ticket["subcategory"]][2] * 0.7, 0.6)
            work_minutes += extra
            resolved = add_working_minutes(t, extra, sched)
            self.log(tid, resolved, "Resolved", group, agent)

        closed = resolved + timedelta(hours=72)

        bounces = len([g for g in groups_visited if g not in ("Service Desk L1", group)])
        reassignment_count = len(groups_visited) - 1 if groups_visited else 0

        resolution_target_h = cfg.SLA_POLICY[priority][1]
        breached = (resolved - ticket["opened_at"]).total_seconds() / 3600 > resolution_target_h

        # Customer survey goes out on resolution; roughly 1 in 5 people answer
        csat = None
        if rng.random() < 0.21:
            score = 4.6 - 1.3 * breached - 0.55 * bounces - 1.1 * reopen_count + rng.normal(0, 0.6)
            csat = int(np.clip(round(score), 1, 5))

        if in_vpn_incident:
            code = "Solved (Workaround)"
        else:
            code = rng.choice(["Solved (Permanently)", "Solved (Workaround)",
                               "Not Solved (Not Reproducible)", "Closed/Resolved by Caller"],
                              p=[0.78, 0.12, 0.04, 0.06])

        status = "Closed"
        if closed > cfg.EXTRACT_TIME:
            status = "Resolved"
            closed = None
        if resolved > cfg.EXTRACT_TIME:
            # Still being worked on when the export ran: drop the future events
            mine = self.events[self.first_event:]
            self.events[self.first_event:] = [e for e in mine if e["event_time"] <= cfg.EXTRACT_TIME]
            status = "In Progress"
            resolved = None
            closed = None
            csat = None
            code = None
        elif closed is not None:
            self.log(tid, closed, "Closed", group)

        ticket.update({
            "status": status,
            "assignment_group": group,
            "assigned_to": agent,
            "first_response_at": first_response if first_response <= cfg.EXTRACT_TIME else None,
            "resolved_at": resolved,
            "closed_at": closed,
            "reassignment_count": reassignment_count,
            "reopen_count": reopen_count,
            "work_minutes": round(work_minutes),
            "resolution_code": code,
            "csat_score": csat,
        })
        self.tickets.append(ticket)

    def cancel(self, ticket, opened):
        tid = ticket["ticket_id"]
        self.log(tid, opened, "Created", "Service Desk L1")
        cancelled = opened + timedelta(minutes=float(rng.uniform(5, 240)))
        self.log(tid, cancelled, "Cancelled", "Service Desk L1")
        ticket.update({
            "status": "Cancelled",
            "assignment_group": "Service Desk L1",
            "assigned_to": None,
            "first_response_at": None,
            "resolved_at": None,
            "closed_at": cancelled,
            "reassignment_count": 0,
            "reopen_count": 0,
            "work_minutes": 0,
            "resolution_code": rng.choice(["Duplicate", "Cancelled by caller"], p=[0.6, 0.4]),
            "csat_score": None,
        })
        self.tickets.append(ticket)


# ---------------------------------------------------------------------------
# Making the export look like a real export
# ---------------------------------------------------------------------------

def add_real_world_mess(tickets):
    """The kind of mess I'd expect to clean in a real ServiceNow extract."""
    utc_shift = timedelta(hours=5, minutes=30)
    for t in tickets:
        # 1. Monitoring integration bug: resolved/closed written in UTC, not IST
        if (t["channel"] == "Monitoring"
                and cfg.UTC_BUG_START <= t["opened_at"] <= cfg.UTC_BUG_END
                and t["resolved_at"] is not None):
            t["resolved_at"] -= utc_shift
            if t["closed_at"] is not None:
                t["closed_at"] -= utc_shift

        # 2. Category typed or mapped inconsistently by an old form
        r = rng.random()
        if r < 0.012:
            t["category"] = t["category"].lower()
        elif r < 0.025:
            t["category"] = t["category"] + " "

    # 3. The export job retried a page and wrote ~0.4% of rows twice
    dupes = rng.choice(len(tickets), size=int(len(tickets) * 0.004), replace=False)
    messy = list(tickets) + [dict(tickets[i]) for i in dupes]
    messy.sort(key=lambda x: x["ticket_id"])
    return messy


def fmt(v):
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if v is None:
        return ""
    return v


def write_csv(path, rows, columns):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for r in rows:
            w.writerow({c: fmt(r.get(c)) for c in columns})
    print(f"  {path.name:<24} {len(rows):>8,} rows")


def main():
    cfg.RAW_DIR.mkdir(parents=True, exist_ok=True)
    print("Generating Tidewater Logistics service desk data for 2025...")

    employees = build_employees()
    agents = build_agents()
    builder = TicketBuilder(employees, agents)

    arrivals = []
    day = cfg.START_DATE.date()
    while day <= cfg.END_DATE.date():
        arrivals.extend(arrival_times(day))
        day += timedelta(days=1)
    arrivals.sort()

    for n, (opened, source) in enumerate(arrivals, start=1):
        builder.build(n, opened, source)

    tickets = add_real_world_mess(builder.tickets)
    events = sorted(builder.events, key=lambda e: (e["ticket_id"], e["event_time"], e["event_id"]))

    groups = [{
        "assignment_group": g,
        "tier": tier,
        "shift_pattern": SHIFT_LABELS[g],
        "is_24x7": sched == "24x7",
        "headcount": hc,
    } for g, (tier, sched, hc) in GROUPS.items()]

    sla = [{
        "priority": p,
        "response_target_min": v[0],
        "resolution_target_hours": v[1],
        "monthly_target_pct": v[2],
    } for p, v in cfg.SLA_POLICY.items()]

    write_csv(cfg.RAW_DIR / "employees.csv", employees,
              ["employee_id", "department", "location", "site_type"])
    write_csv(cfg.RAW_DIR / "agents.csv", agents,
              ["agent_id", "agent_name", "assignment_group", "tier", "joined_on"])
    write_csv(cfg.RAW_DIR / "assignment_groups.csv", groups,
              ["assignment_group", "tier", "shift_pattern", "is_24x7", "headcount"])
    write_csv(cfg.RAW_DIR / "sla_policy.csv", sla,
              ["priority", "response_target_min", "resolution_target_hours", "monthly_target_pct"])
    write_csv(cfg.RAW_DIR / "tickets.csv", tickets, [
        "ticket_id", "opened_at", "channel", "requester_id", "category", "subcategory",
        "priority", "short_description", "status", "assignment_group", "assigned_to",
        "first_response_at", "resolved_at", "closed_at", "reassignment_count",
        "reopen_count", "work_minutes", "resolution_code", "csat_score",
    ])
    write_csv(cfg.RAW_DIR / "ticket_events.csv", events,
              ["event_id", "ticket_id", "event_time", "event_type", "assignment_group", "agent_id"])
    print("Done.")


if __name__ == "__main__":
    main()
