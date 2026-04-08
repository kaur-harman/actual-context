import json, logging, os, re
from google.adk import Agent
from google.adk.tools.tool_context import ToolContext
from db.firestore_client import save_user_profile, get_user_profile

logging.basicConfig(level=logging.INFO)
UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)

def handle_input_tool(tool_context: ToolContext, user_input: str) -> dict:
    """Smart router. Call first with raw user input."""
    text = user_input.strip()
    if UUID_RE.match(text):
        profile = get_user_profile(text)
        if profile:
            tool_context.state["user_id"]        = text
            tool_context.state["user_profile"]   = json.dumps(profile)
            tool_context.state["profile_loaded"] = True
            tool_context.state["stage"]          = ""
            name = profile.get("name", "there")
            return {"action": "loaded", "name": name, "message": f"✅ Welcome back, {name}! Paste any news headline."}
        return {"action": "not_found", "message": "❌ User ID not found. Type 'new' to create a profile."}
    if text.lower() in ["new", "hi", "hello", "hey"]:
        return {"action": "show_form"}
    return {"action": "parse_profile", "raw": text}

def save_profile_tool(
    tool_context: ToolContext,
    name: str, age: int, city: str, sector: str,
    income_lpa: float, loan_amount: float, loan_rate: float, loan_emi: float,
    mf_value: float, mf_type: str, dependents: int, travel_plans: str
) -> dict:
    """Save user financial profile to Firestore."""
    profile = {
        "name": name, "age": age, "city": city, "sector": sector,
        "income_lpa": income_lpa,
        "home_loan":   {"amount": loan_amount, "rate_percent": loan_rate, "emi_monthly": loan_emi},
        "investments": {"mutual_fund_value": mf_value, "mf_type": mf_type},
        "dependents": dependents, "travel_plans": travel_plans
    }
    try:
        user_id = save_user_profile(profile)
        tool_context.state["user_id"]        = user_id
        tool_context.state["user_profile"]   = json.dumps(profile)
        tool_context.state["profile_loaded"] = True
        tool_context.state["stage"]          = ""
        return {"status": "success", "user_id": user_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}

profile_agent = Agent(
    name="profile_agent",
    model=os.getenv("MODEL", "gemini-2.0-flash"),
    description="Handles user profile onboarding and loading",
    instruction="""
You are a fast onboarding assistant.

STEP 1 — ALWAYS call handle_input_tool first with the raw user input.

Read the result:

If action == "loaded":
→ Say exactly the message from the result. Done.

If action == "not_found":
→ Say exactly the message from the result. Done.

If action == "show_form":
→ Say:
"Fill in your details:

Name:
Age:
City:
Sector (IT / banking / manufacturing / govt / other):
Income (LPA):
Home Loan — Amount (₹) | Rate (%) | EMI (₹)  [0 | 0 | 0 if none]
Mutual Funds — Value (₹) | Type (equity/debt/hybrid)  [0 | none if none]
Dependents:
Travel plans in next 6 months (yes/no + destination):"

If action == "parse_profile":
→ Extract all fields from the raw text
→ Call save_profile_tool with extracted values
→ Defaults: loan=0.0/0.0/0.0, mf=0.0/none, dependents=0, travel_plans="none"
→ After save say: "✅ Profile saved, [name]! User ID: [user_id] — save this. Now paste any news headline."

RULES:
- ALWAYS call handle_input_tool first
- Never output raw JSON
- Never ask same question twice
""",
    tools=[handle_input_tool, save_profile_tool],
)
