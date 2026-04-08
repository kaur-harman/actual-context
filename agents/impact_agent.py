import json, logging, os
from google.adk import Agent
from google.adk.tools.tool_context import ToolContext
from db.firestore_client import save_impact_log, get_user_profile, save_flag

logging.basicConfig(level=logging.INFO)

def get_full_context_tool(tool_context: ToolContext) -> dict:
    """Retrieve user profile and news causal chain. Always call first."""
    user_id      = tool_context.state.get("user_id", "")
    profile_json = tool_context.state.get("user_profile", "")
    causal_json  = tool_context.state.get("causal_chain", "{}")
    profile = {}
    if profile_json:
        try:    profile = json.loads(profile_json)
        except: profile = {}
    if (not profile or not profile.get("name") or profile.get("name") == "N/A") and user_id:
        profile = get_user_profile(user_id)
        if profile:
            tool_context.state["user_profile"] = json.dumps(profile)
    causal_chain = {}
    if causal_json:
        try:    causal_chain = json.loads(causal_json)
        except: causal_chain = {}
    return {
        "user_id": user_id, "profile": profile,
        "causal_chain": causal_chain,
        "headline": tool_context.state.get("news_headline", ""),
        "event_id": tool_context.state.get("event_id", "")
    }

def compute_emi_impact_tool(
    tool_context: ToolContext,
    loan_amount: float, current_rate_percent: float,
    rate_change_bps: float, remaining_months: int
) -> dict:
    """Calculate exact EMI change from a rate change in basis points."""
    def emi(p, r, n):
        if n <= 0 or r <= 0: return 0.0
        r = (r/100)/12
        return p*r*(1+r)**n/((1+r)**n-1)
    old = emi(loan_amount, current_rate_percent, remaining_months)
    new = emi(loan_amount, current_rate_percent + rate_change_bps/100, remaining_months)
    delta = new - old
    result = {
        "old_emi": round(old), "new_emi": round(new),
        "monthly_delta": round(delta), "annual_delta": round(delta*12),
        "direction": "increase" if delta > 0 else "decrease"
    }
    tool_context.state["emi_result"] = json.dumps(result)
    return result

def compute_mf_impact_tool(
    tool_context: ToolContext,
    mf_value: float, mf_type: str,
    rate_change_bps: float, event_type: str
) -> dict:
    """Estimate mutual fund portfolio impact."""
    rates = {
        ("debt","monetary_policy"): 0.08, ("equity","monetary_policy"): 0.04,
        ("hybrid","monetary_policy"): 0.05, ("liquid","monetary_policy"): 0.01,
        ("equity","geopolitical"): 0.06, ("equity","commodity"): 0.05,
        ("equity","global_macro"): 0.07,
    }
    pct = rates.get((mf_type.lower(), event_type.lower()), 0.04) * abs(rate_change_bps)
    impact = mf_value * (pct/100)
    result = {
        "mf_value": mf_value, "rupee_impact": round(impact),
        "pct": round(pct,2),
        "direction": "positive" if rate_change_bps < 0 else "negative"
    }
    tool_context.state["mf_result"] = json.dumps(result)
    return result

def save_impact_tool(
    tool_context: ToolContext,
    impact_summary: str, emi_impact_rupees: float, mf_impact_rupees: float,
    sector_impact: str, reasoning_chain: str, should_flag: bool, flag_reason: str
) -> dict:
    """Save impact analysis to Firestore."""
    user_id  = tool_context.state.get("user_id","")
    event_id = tool_context.state.get("event_id","")
    try:
        impact_id = save_impact_log(user_id, event_id, {
            "summary": impact_summary, "emi": emi_impact_rupees,
            "mf": mf_impact_rupees, "sector": sector_impact,
            "reasoning": reasoning_chain, "flagged": should_flag
        })
        if should_flag and user_id and event_id:
            save_flag(user_id, event_id, flag_reason)
        return {"status": "success", "impact_id": impact_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}

impact_agent = Agent(
    name="personal_impact_translator",
    model=os.getenv("MODEL", "gemini-2.0-flash"),
    description="Translates any news into personal rupee impact",
    instruction="""
You are the FINAL agent. Always produce output — never stop silently.

STEP 1: Call get_full_context_tool. Read name, home_loan, investments, sector, income_lpa, causal_chain.

STEP 2: Read event_type from causal_chain.

If event_type == "monetary_policy":
  - loan > 0 → call compute_emi_impact_tool(loan_amount, rate_percent, -25.0, 240)
  - mf > 0   → call compute_mf_impact_tool(mf_value, mf_type, -25.0, "monetary_policy")

If event_type is geopolitical OR commodity OR global_macro:
  - DO NOT call compute_emi_impact_tool
  - mf > 0 → call compute_mf_impact_tool(mf_value, mf_type, 50.0, event_type)

STEP 3: Output:

💰 YOUR PERSONAL IMPACT
[name], here's what this means for your wallet:

🏠 Home Loan: [EMI numbers if computed, else "No direct EMI impact"]
📈 Investments ([mf_type] MF): [₹ impact if computed, else "No MF on record"]
💼 Your Sector ([sector]): [1 sentence]
🛢️ Daily Life: [1 sentence]
🧠 WHY: [mechanism from causal_chain]
⏳ WHEN: [lag_months] months
💡 DO NOW: [one concrete action]

STEP 4: Call save_impact_tool.
Flag if EMI delta > 1000 or MF impact > 5000 or severity == high.

RULES: Real numbers always. Never N/A. Address by name.
""",
    tools=[get_full_context_tool, compute_emi_impact_tool,
           compute_mf_impact_tool, save_impact_tool],
)
