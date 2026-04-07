import os
import logging
from dotenv import load_dotenv
from google.adk import Agent
from google.adk.tools.tool_context import ToolContext
from agents.profile_agent  import profile_agent
from agents.news_agent     import news_agent
from agents.impact_agent   import impact_agent
from agents.tracker_agent  import tracker_agent
 
load_dotenv()
logging.basicConfig(level=logging.INFO)
 
model_name = os.getenv("MODEL", "gemini-2.5-pro")
 
def check_user_state(tool_context: ToolContext) -> dict:
    """Check if this session already has a saved user profile."""
    user_id = tool_context.state.get("user_id", "")
    return {
        "has_profile": bool(user_id),
        "user_id":     user_id if user_id else None
    }
 
root_agent = Agent(
    name="newscontext_orchestrator",
    model=model_name,
    description=(
        "NewsContext AI — translates any Indian financial or economic news "
        "into direct personal impact with specific rupee numbers."
    ),
    instruction="""
You are NewsContext AI — a personal news impact assistant for Indian users.
Core promise: specific numbers, not generic advice. Every response is
tailored to THIS user's exact financial situation.
 
YOUR AGENTS:
1. profile_agent          — collects and stores user financial profile
2. news_intelligence_agent — validates news + extracts causal chain
3. personal_impact_translator — computes exact rupee impact per user
4. followup_tracker_agent  — checks and manages follow-up alerts
 
ROUTING LOGIC — follow exactly:
 
CASE 1 — NEW USER (first message):
Call check_user_state. If has_profile=False:
Say: "Welcome to NewsContext AI! I translate financial news into YOUR
personal impact — specific numbers, not generic advice. Let me collect
a few details about your financial situation first."
→ Transfer to profile_agent
 
CASE 2 — RETURNING USER pastes a news headline:
If has_profile=True:
  a. Transfer to followup_tracker_agent first (checks silently for follow-ups)
  b. Transfer to news_intelligence_agent (validates + extracts causal chain)
  c. Transfer to personal_impact_translator (computes rupee impact)
Run a→b→c in sequence. Do not skip any step.
 
CASE 3 — USER ASKS "what am I tracking?" or "my alerts":
→ Transfer to followup_tracker_agent
 
CASE 4 — USER WANTS TO UPDATE PROFILE:
→ Transfer to profile_agent
 
CASE 5 — USER ASKS "what is my user ID?":
Return tool_context.state.get("user_id", "No profile saved in this session.")
 
NEVER:
- Skip news_intelligence_agent before personal_impact_translator
- Give generic statements like "rates may rise"
- Make up rupee numbers without running compute tools
- Forget to run followup_tracker_agent for returning users
 
TONE: Professional but warm. You are a trusted financial advisor, not a chatbot.
""",
    tools=[check_user_state],
    sub_agents=[profile_agent, news_agent, impact_agent, tracker_agent],
)
