import json
import logging
from google.adk import Agent
from google.adk.tools.tool_context import ToolContext
from db.client import save_user_profile, get_user_profile

logging.basicConfig(level=logging.INFO)

# ── Tools ──────────────────────────────────────────────────────────────────

def save_profile_tool(
    tool_context: ToolContext,
    name: str,
    age: int,
    city: str,
    income_lpa: float,
    sector: str,
    home_loan_amount: float,
    home_loan_rate: float,
    home_loan_emi: float,
    mutual_fund_value: float,
    mf_type: str,
    dependents: int
) -> dict:
    """
    Saves the user profile to AlloyDB after collecting all details.
    Call this once you have parsed all fields from the user's response.
    """
    profile = {
        "name": name,
        "age": age,
        "city": city,
        "income_lpa": income_lpa,
        "sector": sector,
        "home_loan": {
            "amount": home_loan_amount,
            "rate_percent": home_loan_rate,
            "emi_monthly": home_loan_emi
        },
        "investments": {
            "mutual_fund_value": mutual_fund_value,
            "mf_type": mf_type
        },
        "dependents": dependents
    }
    try:
        user_id = save_user_profile(profile)
        tool_context.state["user_id"] = user_id
        tool_context.state["user_profile"] = json.dumps(profile)
        logging.info(f"[ProfileAgent] Saved profile. user_id={user_id}")
        return {"status": "success", "user_id": user_id}
    except Exception as e:
        logging.error(f"[ProfileAgent] Save failed: {e}")
        return {"status": "error", "message": str(e)}

def load_profile_tool(
    tool_context: ToolContext,
    user_id: str
) -> dict:
    """Load an existing user profile by user_id."""
    try:
        profile = get_user_profile(user_id)
        if profile:
            tool_context.state["user_id"] = user_id
            tool_context.state["user_profile"] = json.dumps(profile)
            return {"status": "found", "profile": profile}
        return {"status": "not_found"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ── Agent ──────────────────────────────────────────────────────────────────

profile_agent = Agent(
    name="profile_agent",
    model="gemini-2.5-flash",
    description=(
        "Collects personal financial and demographic context from the user "
        "to enable personalised news impact analysis."
    ),
    instruction="""
You are a friendly financial context collector for NewsContext AI.
Your job is to collect the user's profile in a SINGLE prompt — ask everything at once.

STEP 1 — Send this exact message to the user:

"To personalise your news impact, I need a few quick details. Please fill in the form below:

• Name:
• Age & City:
• Work sector (IT / banking / manufacturing / govt / other):
• Annual income (LPA):
• Home loan — Amount (₹) | Interest rate (%) | Monthly EMI (₹)  [enter 0 | 0 | 0 if none]
• Mutual funds — Current value (₹) | Type (equity / debt / hybrid)  [enter 0 | none if none]
• Number of dependents (spouse, children, parents):"

STEP 2 — Once the user replies, parse all fields from their response.
If any field is missing or unclear, ask only for the missing fields (not the whole form again).

STEP 3 — Call save_profile_tool with all parsed values.
For missing home loan or MF values, default to 0 / "none".

STEP 4 — Confirm: "Your profile is saved! You can now paste any news headline
and I'll tell you exactly how it affects you."

If the user says they already have a profile, ask for their user_id and call load_profile_tool.
""",
    tools=[save_profile_tool, load_profile_tool],
)