"""
WeCare FastAPI — Application Constants

config/constants + helpers/booking_workflow
"""

# ── JWT Token Expiry (Route: constants L20–21) ──
ACCESS_TOKEN_EXPIRE_SECONDS: int = 3600      # 1 hour
REFRESH_TOKEN_EXPIRE_SECONDS: int = 604800   # 7 days

# ── Booking Workflow State Machine (Route: booking_workflow L9–18) ──
# Exact reproduction of booking_workflow_allowed_transitions()
BOOKING_ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    "pending": ["accepted", "declined", "cancelled"],
    "accepted": ["in_progress", "cancelled"],
    "in_progress": ["completed"],
    "completed": [],
    "declined": [],
    "cancelled": [],
}

# ── Payout Hold Period (Route: booking_workflow L117) ──
PAYOUT_HOLD_HOURS: int = 24

# ── OTP Defaults ──
OTP_MAX_ATTEMPTS: int = 5

# ── Health Endpoint ──
APP_NAME: str = "WeCare API"
APP_VERSION: str = "Demo Prototype"
API_BASE_PATH: str = "/api/v1"

# ── Allowed APP_ENV values (Route: health L21) ──
ALLOWED_ENVIRONMENTS: list[str] = ["local", "development", "staging", "production"]
