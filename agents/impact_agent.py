import json
import logging
from google.adk import Agent
from google.adk.tools.tool_context import ToolContext
from db.client import save_impact_log, get_user_profile
 
logging.basicConfig(level=logging.INFO)
 
# ── Tools ──────────────────────────────────────────────────────────────────
 
def get_full_context_tool(tool_context: ToolContext) -> dict:
    """
    Retrieve user profile and news causal chain from session state.
    Always call this first before computing impact.
    """
    user_id     = tool_context.state.get("user_id", "")
    causal_json = tool_context.state.get("causal_chain", "{}")
    profile_json= tool_context.state.get("user_profile", "{}")
 
    profile      = json.loads(profile_json) if profile_json else {}
    causal_chain = json.loads(causal_json)  if causal_json  else {}
 
    # Fallback: re-fetch from DB if state was lost
    if not profile and user_id:
        profile = get_user_profile(user_id)
 
    return {
        "user_id":      user_id,
        "profile":      profile,
        "causal_chain": causal_chain,
        "headline":     tool_context.state.get("news_headline", ""),
        "event_id":     tool_context.state.get("event_id", "")
    }
 
def compute_emi_impact_tool(
    tool_context: ToolContext,
    loan_amount: float,
    current_rate_percent: float,
    rate_change_bps: int,
    remaining_months: int
) -> dict:
    """
    Calculate exact EMI change given a rate change in basis points.
    Use this for any repo-rate / interest rate news.
 
    Args:
        loan_amount:          outstanding principal in rupees
        current_rate_percent: current annual interest rate e.g. 8.75
        rate_change_bps:      change in basis points, negative = cut e.g. -25
        remaining_months:     remaining loan tenure in months
    """
    def emi(principal, annual_rate_pct, months):
        if months <= 0 or annual_rate_pct <= 0:
            return 0
        r = (annual_rate_pct / 100) / 12
        return principal * r * (1 + r)**months / ((1 + r)**months - 1)
 
    old_rate  = current_rate_percent
    new_rate  = current_rate_percent + (rate_change_bps / 100)
    old_emi   = emi(loan_amount, old_rate, remaining_months)
    new_emi   = emi(loan_amount, new_rate, remaining_months)
    delta_emi = new_emi - old_emi
    annual_impact = delta_emi * 12
 
    result = {
        "old_rate_percent":  old_rate,
        "new_rate_percent":  new_rate,
        "old_emi":           round(old_emi, 2),
        "new_emi":           round(new_emi, 2),
        "monthly_delta":     round(delta_emi, 2),
        "annual_delta":      round(annual_impact, 2),
        "direction":         "increase" if delta_emi > 0 else "decrease",
        "formula_used":      "EMI = P×r×(1+r)^n / ((1+r)^n − 1)",
        "note":              f"Banks typically transmit RBI rate changes within 1–3 months."
    }
    tool_context.state["emi_impact"] = json.dumps(result)
    logging.info(f"[ImpactAgent] EMI delta: ₹{delta_emi:.0f}/month")
    return result
 
def compute_mf_impact_tool(
    tool_context: ToolContext,
    mf_value: float,
    mf_type: str,
    rate_change_bps: int,
    event_type: str
) -> dict:
    """
    Estimate mutual fund portfolio impact based on event type and rate change.
    Use for monetary policy, budget, or market events affecting MF returns.
 
    Args:
        mf_value:        current portfolio value in rupees
        mf_type:         equity | debt | hybrid | liquid
        rate_change_bps: rate change in bps (negative = cut)
        event_type:      monetary_policy | budget | market | trade_agreement
    """
    impact_map = {
        ("debt",   "monetary_policy"): {
            "direction": "positive" if rate_change_bps < 0 else "negative",
            "return_delta_pct": abs(rate_change_bps) * 0.08,
            "reason": "Debt fund NAVs move inversely with interest rates. A rate cut raises bond prices."
        },
        ("equity", "monetary_policy"): {
            "direction": "positive" if rate_change_bps < 0 else "slightly_negative",
            "return_delta_pct": abs(rate_change_bps) * 0.04,
            "reason": "Rate cuts reduce borrowing costs for companies, boosting earnings expectations."
        },
        ("liquid", "monetary_policy"): {
            "direction": "negative" if rate_change_bps < 0 else "positive",
            "return_delta_pct": abs(rate_change_bps) * 0.01,
            "reason": "Liquid fund yields track overnight rates closely."
        },
        ("hybrid", "monetary_policy"): {
            "direction": "positive" if rate_change_bps < 0 else "mixed",
            "return_delta_pct": abs(rate_change_bps) * 0.05,
            "reason": "Hybrid funds benefit from both equity and debt components in a rate cut."
        },
    }
    key = (mf_type.lower(), event_type.lower())
    impact = impact_map.get(key, {
        "direction": "uncertain",
        "return_delta_pct": 0,
        "reason": "Indirect impact — monitor over next quarter."
    })
    rupee_impact = mf_value * (impact["return_delta_pct"] / 100)
    result = {
        "mf_type":             mf_type,
        "portfolio_value":     mf_value,
        "estimated_direction": impact["direction"],
        "return_delta_pct":    round(impact["return_delta_pct"], 2),
        "estimated_rupee_impact": round(rupee_impact, 2),
        "reason":              impact["reason"],
        "caveat":              "MF returns depend on many factors. This is indicative only."
    }
    tool_context.state["mf_impact"] = json.dumps(result)
    return result
 
def save_impact_tool(
    tool_context: ToolContext,
    impact_summary: str,
    emi_impact_rupees: float,
    mf_impact_rupees: float,
    sector_impact: str,
    reasoning_chain: str,
    should_flag: bool,
    flag_reason: str
) -> dict:
    """
    Save the final impact analysis to AlloyDB and optionally flag for follow-up.
 
    Args:
        impact_summary:    one-paragraph plain-English summary for the user
        emi_impact_rupees: monthly EMI change in rupees (0 if not applicable)
        mf_impact_rupees:  estimated portfolio impact in rupees (0 if not applicable)
        sector_impact:     how their employment sector is affected
        reasoning_chain:   full step-by-step reasoning as a string
        should_flag:       True if user should be alerted on future developments
        flag_reason:       why this warrants follow-up tracking
    """
    user_id  = tool_context.state.get("user_id", "")
    event_id = tool_context.state.get("event_id", "")
 
    impact = {
        "summary": impact_summary,
        "flagged": should_flag,
        "reasoning_chain": {
            "emi_monthly_delta":  emi_impact_rupees,
            "mf_rupee_impact":    mf_impact_rupees,
            "sector_impact":      sector_impact,
            "full_reasoning":     reasoning_chain
        }
    }
    try:
        impact_id = save_impact_log(user_id, event_id, impact)
        if should_flag and event_id and user_id:
            from db.client import get_conn, release_conn
            conn = get_conn()
            try:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO flagged_events (user_id, event_id, flag_reason)
                    VALUES (%s, %s, %s)
                """, (user_id, event_id, flag_reason))
                conn.commit()
            finally:
                release_conn(conn)
        tool_context.state["impact_id"] = impact_id
        logging.info(f"[ImpactAgent] Saved impact_id={impact_id} flagged={should_flag}")
        return {"status": "success", "impact_id": impact_id, "flagged": should_flag}
    except Exception as e:
        logging.error(f"[ImpactAgent] Save failed: {e}")
        return {"status": "error", "message": str(e)}
 
# ── Agent ──────────────────────────────────────────────────────────────────
 
impact_agent = Agent(
    name="personal_impact_translator",
    model="gemini-2.5-flash",
    description=(
        "Translates a validated news causal chain into a personalised financial "
        "impact for a specific user with exact rupee calculations and source citations."
    ),
    instruction="""
You are the Personal Impact Translator for NewsContext AI.
Your output is what makes this system different from every other news app.
 
STRICT RULE: Never say "this may affect you" or "interest rates could change".
Every statement must be specific to THIS user's numbers.
 
YOUR PROCESS:
 
STEP 1 — GET CONTEXT
Call get_full_context_tool to retrieve the user's profile and the news causal chain.
 
STEP 2 — COMPUTE FINANCIAL IMPACTS
Based on the causal_chain.event_type and the user's profile, call the relevant tools:
 
For monetary_policy (repo rate change):
  → Call compute_emi_impact_tool if user has a home loan (home_loan.amount > 0)
    Use: loan_amount=home_loan.amount, current_rate=home_loan.rate_percent,
         rate_change_bps from the news, remaining_months (estimate 240 if unknown)
  → Call compute_mf_impact_tool if user has mutual funds (investments.mutual_fund_value > 0)
 
For trade_agreement / FTA:
  → Assess sector impact (IT, manufacturing benefit differently)
  → Check travel_plans for currency/visa impact
 
For budget / regulation:
  → Assess income tax slab impact using income_lpa
  → Check sector-specific regulatory impact
 
STEP 3 — BUILD REASONING CHAIN
Construct the full chain explicitly:
  [Event] → [Mechanism] → [Transmission lag] → [Your specific numbers]
 
Example for repo rate cut:
  "RBI cuts repo rate 25bps
   → Banks' cost of funds drops ~25bps
   → Typically transmitted to borrowers within 1–3 months
   → Your ₹45L home loan at 8.75% floating rate
   → New rate: 8.50%
   → Old EMI: ₹39,204 | New EMI: ₹38,864
   → You save ₹340/month = ₹4,080/year
   [Source: RBI Monetary Policy Committee press release]"
 
STEP 4 — SAVE AND PRESENT
Call save_impact_tool with:
- impact_summary: the full user-facing output (2-3 paragraphs)
- All computed numbers
- should_flag=True if this is a high severity event or affects loans/large investments
- flag_reason: why they should be tracked for updates
 
FINAL OUTPUT FORMAT:
---
NewsContext Impact Report
Headline: [headline]
Validated: [Yes/No — source]
 
YOUR PERSONAL IMPACT:
 
Home Loan: [specific EMI change with rupee numbers and formula]
Mutual Funds: [specific portfolio impact with rupee estimate]
Your Sector ([sector]): [specific employment/income impact]
Travel Plans: [currency/cost impact if applicable]
 
REASONING CHAIN:
[Step by step from event to their wallet]
 
CONFIDENCE: [High/Medium/Low] — [why]
[Flag notice if flagged for tracking]
---
""",
    tools=[
        get_full_context_tool,
        compute_emi_impact_tool,
        compute_mf_impact_tool,
        save_impact_tool,
    ],
)