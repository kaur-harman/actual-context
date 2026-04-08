import os, uuid, logging
from google.cloud import firestore
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Lazy singleton — avoids init crash at import time
_db = None
def get_db():
    global _db
    if _db is None:
        _db = firestore.Client(project=os.getenv("PROJECT_ID"))
    return _db

# ── Users ──────────────────────────────────────────────────────────────────

def save_user_profile(profile: dict) -> str:
    user_id = str(uuid.uuid4())
    get_db().collection("users").document(user_id).set(profile)
    logger.info(f"[DB] saved user {user_id}")
    return user_id

def get_user_profile(user_id: str) -> dict:
    doc = get_db().collection("users").document(user_id).get()
    return doc.to_dict() if doc.exists else {}

# ── Events ─────────────────────────────────────────────────────────────────

def save_news_event(event: dict) -> str:
    event_id = str(uuid.uuid4())
    get_db().collection("events").document(event_id).set(event)
    logger.info(f"[DB] saved event {event_id}")
    return event_id

# ── Impact logs ────────────────────────────────────────────────────────────

def save_impact_log(user_id: str, event_id: str, impact: dict) -> str:
    impact_id = str(uuid.uuid4())
    get_db().collection("impacts").document(impact_id).set({
        "user_id":  user_id,
        "event_id": event_id,
        "impact":   impact
    })
    return impact_id

# ── Flags ──────────────────────────────────────────────────────────────────

def save_flag(user_id: str, event_id: str, reason: str):
    get_db().collection("flags").add({
        "user_id":  user_id,
        "event_id": event_id,
        "reason":   reason,
        "resolved": False
    })
    logger.info(f"[DB] flagged event {event_id} for user {user_id}")

def get_flags(user_id: str) -> list:
    docs = get_db().collection("flags")\
        .where("user_id", "==", user_id)\
        .where("resolved", "==", False)\
        .stream()
    return [d.to_dict() for d in docs]