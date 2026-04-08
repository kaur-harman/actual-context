import os, logging, re, json
from typing import List
from dotenv import load_dotenv
from google.adk import Agent
from google.adk.tools.tool_context import ToolContext
from agents.profile_agent import profile_agent
from agents.impact_agent  import impact_agent
from tools.mcp_tools import validate_news_from_feeds, get_rbi_repo_rate_context
from db.firestore_client import save_news_event

load_dotenv()
logging.basicConfig(level=logging.INFO)
model_name = os.getenv("MODEL", "gemini-2.0-flash")
UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)

def check_user_state(tool_context: ToolContext) -> dict:
    return {
        "has_profile": bool(tool_context.state.get("user_id")),
        "stage":       tool_context.state.get("stage", "")
    }

def is_uuid(tool_context: ToolContext, text: str) -> dict:
    return {"is_uuid": bool(UUID_RE.match(text.strip()))}

def set_stage(tool_context: ToolContext, stage: str) -> dict:
    tool_context.state["stage"] = stage
    return {"stage": stage}

def process_news_tool(tool_context: ToolContext, headline: str) -> dict:
    validation = validate_news_from_feeds(headline)
    tool_context.state["news_headline"] = headline
    tool_context.state["news_validated"] = validation.get("validated", False)
    rbi_context = {}
    if any(k in headline.lower() for k in ["rbi","repo","rate","inflation","mpc","bps"]):
        rbi_context = get_rbi_repo_rate_context()
        tool_context.state["rbi_context"] = json.dumps(rbi_context)
    event_id = save_news_event({
        "headline": headline, "source_url": "",
        "validated": validation.get("validated", False),
        "causal_chain": {}, "affected_sectors": []
    })
    tool_context.state["event_id"] = event_id
    return {
        "headline": headline,
        "validated": validation.get("validated", False),
        "confidence": validation.get("confidence", "low"),
        "sources": validation.get("matched_sources", []),
        "rbi_context": rbi_context,
        "event_id": event_id
    }

def save_causal_chain_tool(
    tool_context: ToolContext,
    event_type: str,
    mechanism: str,
    affected_sectors: List[str],
    lag_months: int,
    severity: str,
    summary: str
) -> dict:
    causal_chain = {
        "event_type": event_type,
        "mechanism": mechanism,
        "affected_sectors": affected_sectors,
        "lag_months": lag_months,
        "severity": severity,
        "summary": summary
    }
    tool_context.state["causal_chain"] = json.dumps(causal_chain)
    return {"status": "saved", "causal_chain": causal_chain}

root_agent = Agent(
    name="newscontext_orchestrator",
    model=model_name,
    description="NewsContext AI — any news into personal rupee impact",
    instruction="""
You are NewsContext AI. You translate any news into personal rupee impact.

EVERY TURN:
1. Call check_user_state
2. Call is_uuid with user input

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STAGE CHECK (always first)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If stage == "impact":
  Transfer to personal_impact_translator
  Call set_stage("")
  STOP

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NO PROFILE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If has_profile == False:
  If is_uuid == True → Transfer to profile_agent → STOP
  If input == "new"  → Transfer to profile_agent → STOP
  Else → Say:
    "Welcome to NewsContext AI.
    I translate ANY news — rates, wars, oil, trade — into your personal ₹ impact.
    Paste your user ID or type 'new' to set up your profile."
  STOP

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HAS PROFILE + stage == ""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If input is "hi"/"hello"/"hey":
  Say: "Profile loaded. Paste any news headline." → STOP

If input is "update profile":
  Transfer to profile_agent → STOP

If is_uuid == True:
  Say: "Profile already loaded. Paste a news headline." → STOP

OTHERWISE (news headline):
  Do ALL 5 steps in ONE turn:

  1. Call process_news_tool with the headline
  2. Extract causal chain:
     event_type: monetary_policy | geopolitical | commodity | trade_agreement | global_macro | budget | regulation
     mechanism: ONE sentence
     affected_sectors: list
     lag_months: integer 0-12
     severity: low | medium | high
     summary: 1-2 sentences
  3. Call save_causal_chain_tool
  4. Call set_stage("impact")
  5. Transfer to personal_impact_translator

  CRITICAL: All 5 steps in ONE turn. Never stop between them.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Stage check always first
- Never re-store headline or loop
- Never output text while processing news
""",
    tools=[check_user_state, is_uuid, set_stage, process_news_tool, save_causal_chain_tool],
    sub_agents=[profile_agent, impact_agent],
)
