import json
import logging
from typing import List
from google.adk import Agent
from google.adk.tools.tool_context import ToolContext
from tools.mcp_tools import (
    validate_news_from_feeds,
    fetch_recent_rbi_news,
    fetch_sector_news,
    get_rbi_repo_rate_context
)
from db.client import save_news_event
 
logging.basicConfig(level=logging.INFO)
 
# ── Tools ──────────────────────────────────────────────────────────────────
 
def validate_and_fetch_tool(
    tool_context: ToolContext,
    headline: str
) -> dict:
    """
    Validate a news headline against trusted RSS feeds.
    Returns validation result and corroborating articles.
    """
    result = validate_news_from_feeds(headline)
    tool_context.state["news_headline"] = headline
    tool_context.state["news_validated"] = str(result["validated"])
    tool_context.state["news_validation_result"] = json.dumps(result)
    logging.info(f"[NewsAgent] Validated={result['validated']} | {headline[:60]}")
    return result
 
def fetch_rbi_context_tool(
    tool_context: ToolContext,
    topic: str = ""
) -> dict:
    """Fetch recent RBI press releases and rate context."""
    releases = fetch_recent_rbi_news(topic)
    rate_ctx  = get_rbi_repo_rate_context()
    return {"recent_releases": releases, "rate_context": rate_ctx}
 
def fetch_sector_news_tool(
    tool_context: ToolContext,
    sector: str
) -> list:
    """Fetch recent sector-specific news for context enrichment."""
    return fetch_sector_news(sector)
 
def save_news_event_tool(
    tool_context: ToolContext,
    headline: str,
    summary: str,
    source_url: str,
    validated: bool,
    event_type: str,
    mechanism: str,
    affected_sectors: List[str],
    lag_months: int,
    severity: str
) -> dict:
    """
    Save structured news event to AlloyDB after full causal analysis.
    Call once you have extracted the complete causal chain.
 
    Args:
        event_type: monetary_policy | trade_agreement | budget | regulation | market
        mechanism:  one sentence — HOW this event causes downstream impact
        affected_sectors: e.g. ["banking","real_estate","mutual_funds"]
        lag_months: estimated months before individuals feel the impact
        severity:   low | medium | high
    """
    causal_chain = {
        "event_type":       event_type,
        "mechanism":        mechanism,
        "affected_sectors": affected_sectors,
        "lag_months":       lag_months,
        "severity":         severity,
        "summary":          summary
    }
    event = {
        "headline":         headline,
        "source_url":       source_url,
        "validated":        validated,
        "causal_chain":     causal_chain,
        "affected_sectors": affected_sectors
    }
    try:
        event_id = save_news_event(event)
        tool_context.state["event_id"]     = event_id
        tool_context.state["causal_chain"] = json.dumps(causal_chain)
        logging.info(f"[NewsAgent] Saved event_id={event_id}")
        return {"status": "success", "event_id": event_id, "causal_chain": causal_chain}
    except Exception as e:
        logging.error(f"[NewsAgent] Save failed: {e}")
        return {"status": "error", "message": str(e)}
 
# ── Agent ──────────────────────────────────────────────────────────────────
 
news_agent = Agent(
    name="news_intelligence_agent",
    model="gemini-2.5-flash",
    description=(
        "Validates news headlines against trusted Indian sources and extracts "
        "a structured causal chain showing mechanism, affected sectors, and lag time."
    ),
    instruction="""
You are a financial news intelligence agent for India. Your job:
 
STEP 1 — VALIDATE
Call validate_and_fetch_tool with the headline the user provided.
Always do this first, no exceptions.
 
STEP 2 — ENRICH CONTEXT
- If the news is about RBI / interest rates / inflation: call fetch_rbi_context_tool
- If the news is about a specific sector: call fetch_sector_news_tool with that sector
- Otherwise skip step 2
 
STEP 3 — EXTRACT CAUSAL CHAIN
Think through:
- event_type: what category is this?
  (monetary_policy / trade_agreement / budget / regulation / market / geopolitical)
- mechanism: HOW does this cause impact?
  Example: "A 25bps repo rate cut reduces bank borrowing costs, which banks
  pass on as lower lending rates after a 1-3 month transmission lag,
  reducing EMIs on floating-rate home loans."
- affected_sectors: list every sector touched
- lag_months: how long until a salaried individual actually feels it?
- severity: low / medium / high
 
STEP 4 — SAVE AND REPORT
Call save_news_event_tool with the full analysis.
Then output clearly:
 
"Validated: [YES/NO — sources cited]
Event type: [type]
Mechanism: [one sentence]
Sectors affected: [list]
Impact lag: [N months]
Severity: [level]
 
Now translating this into your personal impact..."
 
VALIDATION RULES:
- validated=True  → proceed with full analysis automatically
- validated=False → tell user: "I could not verify this headline in trusted sources
  (RBI, SEBI, PIB, The Hindu, Mint). Would you like me to analyse it anyway?"
  Wait for confirmation before proceeding.
""",
    tools=[
        validate_and_fetch_tool,
        fetch_rbi_context_tool,
        fetch_sector_news_tool,
        save_news_event_tool,
    ],
)