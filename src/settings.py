"""
Shared settings for the project.

Everything that is an assumption (contract value, staff cost, SLA targets)
lives here so it's easy to find and easy to argue with. If you think a number
is wrong, change it here and re-run; nothing else is hard-coded.
"""

from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
IMAGES_DIR = ROOT / "images"

SEED = 42

# Ticket window. The export was "taken" on the morning of 2 Jan 2026,
# so anything still being worked on at that time shows up as open.
START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 12, 31, 23, 59, 59)
EXTRACT_TIME = datetime(2026, 1, 2, 9, 0, 0)

# SLA policy from the (fictional) contract. Clock runs in calendar time.
SLA_POLICY = {
    # priority: (response target in minutes, resolution target in hours, monthly compliance target %)
    "P1": (15, 4, 95),
    "P2": (30, 8, 95),
    "P3": (240, 48, 90),
    "P4": (480, 120, 90),
}

# Commercials. These are my assumptions for a mid-size managed service
# contract in India, not numbers from a real deal.
MONTHLY_CONTRACT_FEE_INR = 38_00_000          # 38 lakh per month
SERVICE_CREDIT_PER_MISS_PCT = 2.5             # per priority that misses its monthly target
SERVICE_CREDIT_CAP_PCT = 10.0                 # max credit in any month

L1_COST_PER_HOUR_INR = 420                    # loaded cost (salary + overheads)
L2_COST_PER_HOUR_INR = 650
NIGHT_SHIFT_PREMIUM = 1.15
PRODUCTIVE_HOURS_PER_FTE_YEAR = 1_920
WAREHOUSE_WORKER_COST_PER_HOUR_INR = 110      # what an idle picker/packer costs the client
SSPR_ADOPTION = 0.70                          # share of resets people would actually self-serve

# Note: sql/05_powerbi_views.sql repeats the fee and credit rule in the
# monthly_sla view (38 lakh, 2.5% per miss, 10% cap). Change both together.

# Known events in 2025 that show up in the data
VPN_INCIDENT_START = datetime(2025, 7, 14)    # VPN client v5.2 pushed to all laptops
VPN_INCIDENT_END = datetime(2025, 8, 25)      # v5.2.3 hotfix rolled out

# The monitoring tool's integration wrote resolved/closed times in UTC
# instead of IST for about six weeks. Found during data cleaning.
UTC_BUG_START = datetime(2025, 3, 1)
UTC_BUG_END = datetime(2025, 4, 15, 23, 59, 59)

# Local Postgres connection used by load_to_postgres.py.
# Override with environment variables if yours is different.
PG_DEFAULTS = {
    "host": "localhost",
    "port": 5432,
    "dbname": "servicedesk",
    "user": "postgres",
    "password": "",
}
