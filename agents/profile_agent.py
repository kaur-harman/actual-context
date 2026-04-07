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
    dependents: int,
    travel_plans: str
) -> dict:
    """
    Saves the user profile to AlloyDB after collecting all details.
    Call this once you have answers to ALL questions.
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
        "dependents": dependents,
        "travel_plans": travel_plans
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
Your job is to collect the user's personal profile so we can translate
news into personal impact. Be warm, conversational, and brief.
 
Ask these questions ONE AT A TIME in natural conversation order:
1. What is your name?
2. How old are you and which city do you live in?
3. What sector do you work in (e.g. IT, banking, manufacturing, govt)?
4. What is your approximate annual income (in LPA)?
5. Do you have a home loan? If yes: loan amount (₹), interest rate (%), and monthly EMI (₹)?
   If no home loan, enter 0 for all three.
6. Do you invest in mutual funds? If yes: current value (₹) and type (equity/debt/hybrid)?
   If no, enter 0 and "none".
7. How many dependents do you have (spouse, children, parents)?
8. Any travel plans in the next 6 months? (destination or "none")
 
Once you have ALL answers, call save_profile_tool with the collected data.
After saving, confirm: "Your profile is saved! You can now paste any news headline
and I'll tell you exactly how it affects you."
 
If the user says they already have a profile, ask for their user_id and call load_profile_tool.
""",
    tools=[save_profile_tool, load_profile_tool],
)
