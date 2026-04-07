import json
import logging
from google.adk import Agent
from google.adk.tools.tool_context import ToolContext
from db.client import check_flagged_events, get_conn, release_conn
 
logging.basicConfig(level=logging.INFO)
 
# ── Tools ──────────────────────────────────────────────────────────────────
 
def check_followups_tool(tool_context: ToolContext) -> dict:
    """
    Check if the current news headline relates to any previously flagged events
    for this user. Uses AlloyDB ai.if() for semantic matching inside SQL.
    Call this on every new news input for returning users.
    """
    user_id  = tool_context.state.get("user_id", "")
    headline = tool_context.state.get("news_headline", "")
 
    if not user_id or not headline:
        return {"has_followups": False, "matches": []}
 
    try:
        matches = check_flagged_events(user_id, headline)
        result  = {"has_followups": len(matches) > 0, "matches": matches}
        tool_context.state["followup_matches"] = json.dumps(matches)
        logging.info(f"[TrackerAgent] Found {len(matches)} follow-up match(es)")
        return result
    except Exception as e:
        logging.error(f"[TrackerAgent] check_followups error: {e}")
        return {"has_followups": False, "matches": [], "error": str(e)}
 
def get_all_flagged_tool(tool_context: ToolContext) -> list:
    """List all currently flagged events for this user (unresolved)."""
    user_id = tool_context.state.get("user_id", "")
    if not user_id:
        return []
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT fe.flag_id, ne.headline, fe.flag_reason, fe.created_at
            FROM flagged_events fe
            JOIN news_events ne ON fe.event_id = ne.event_id
            WHERE fe.user_id = %s AND fe.resolved = FALSE
            ORDER BY fe.created_at DESC
        """, (user_id,))
        rows = cur.fetchall()
        return [
            {"flag_id": str(r[0]), "headline": r[1],
             "reason": r[2], "flagged_on": str(r[3])}
            for r in rows
        ]
    except Exception as e:
        logging.error(f"[TrackerAgent] get_all_flagged error: {e}")
        return []
    finally:
        release_conn(conn)
 
def resolve_flag_tool(
    tool_context: ToolContext,
    flag_id: str
) -> dict:
    """Mark a flagged event as resolved (user no longer needs updates on it)."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE flagged_events SET resolved = TRUE
            WHERE flag_id = %s
        """, (flag_id,))
        conn.commit()
        return {"status": "resolved", "flag_id": flag_id}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        release_conn(conn)
 
# ── Agent ──────────────────────────────────────────────────────────────────
 
tracker_agent = Agent(
    name="followup_tracker_agent",
    model="gemini-2.5-flash",
    description=(
        "Tracks flagged news events and resurfaces them when related "
        "developments appear, using AlloyDB semantic matching."
    ),
    instruction="""
You are the Follow-up Tracker for NewsContext AI.
 
You run automatically on every news input for returning users.
Your job is to check if new news is a development of something the user
previously flagged as important.
 
PROCESS:
 
STEP 1 — CHECK FOR MATCHES
Call check_followups_tool immediately.
 
STEP 2A — IF MATCHES FOUND:
Alert the user BEFORE the new impact analysis:
 
"FOLLOW-UP ALERT: This news appears to be a development of an event
you were tracking:
  Original: [original_headline]
  Why you flagged it: [flag_reason]
 
This is an update — here is how it changes your situation..."
 
Then proceed with the new impact analysis as normal.
 
STEP 2B — IF NO MATCHES:
Say nothing about follow-ups. Proceed silently.
 
STEP 3 — IF USER ASKS "what am I tracking?":
Call get_all_flagged_tool and list their flagged events clearly.
 
STEP 4 — IF USER SAYS "stop tracking [topic]":
Call resolve_flag_tool with the relevant flag_id.
 
IMPORTANT: This agent runs silently in the background for normal news inputs.
Only speak up when there is a genuine follow-up match.
""",
    tools=[check_followups_tool, get_all_flagged_tool, resolve_flag_tool],
)
