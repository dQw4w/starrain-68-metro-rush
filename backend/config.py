import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL: str = os.environ["DATABASE_URL"]

# PIN for the single super-admin account — checked live on every login
# attempt (see auth.verify_superadmin_pin), never stored in the DB. Change
# this and redeploy to change the live PIN immediately.
SUPERADMIN_BOOTSTRAP_PIN: str = os.environ.get("SUPERADMIN_BOOTSTRAP_PIN", "2735")

SESSION_TTL_HOURS: int = int(os.environ.get("SESSION_TTL_HOURS", "18"))
WS_TICKET_TTL_SECONDS: int = int(os.environ.get("WS_TICKET_TTL_SECONDS", "30"))
