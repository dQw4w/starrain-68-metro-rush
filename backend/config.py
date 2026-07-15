import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL: str = os.environ["DATABASE_URL"]

# Bootstrap PIN for the single super-admin account, seeded on first startup if no
# super-admin (admins row with team_id IS NULL) exists yet. Change this in .env
# for anything beyond local testing.
SUPERADMIN_BOOTSTRAP_PIN: str = os.environ.get("SUPERADMIN_BOOTSTRAP_PIN", "0000")

SESSION_TTL_HOURS: int = int(os.environ.get("SESSION_TTL_HOURS", "18"))
WS_TICKET_TTL_SECONDS: int = int(os.environ.get("WS_TICKET_TTL_SECONDS", "30"))
