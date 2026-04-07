import os
import json
import logging
import requests
import feedparser
from dotenv import load_dotenv
 
load_dotenv()
logging.basicConfig(level=logging.INFO)
 
# Trusted Indian news RSS feeds for validation
TRUSTED_FEEDS = {
    "rbi":    "https://www.rbi.org.in/Scripts/RSSFeed.aspx?Id=18",
    "pib":    "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",
    "hindu":  "https://www.thehindu.com/business/Economy/feeder/default.rss",
    "mint":   "https://www.livemint.com/rss/economy",
    "sebi":   "https://www.sebi.gov.in/sebirss.xml",
}
 
def validate_news_from_feeds(headline: str) -> dict:
    """
    Search trusted RSS feeds for corroboration of a given headline.
    Returns validation result with matched sources.
    """
    headline_words = set(headline.lower().split())
    matches = []
 
    for source, url in TRUSTED_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:20]:
                title_words = set(entry.get("title", "").lower().split())
                overlap = len(headline_words & title_words)
                if overlap >= 3:
                    matches.append({
                        "source": source,
                        "title": entry.get("title", ""),
                        "link":  entry.get("link", ""),
                        "overlap_score": overlap
                    })
        except Exception as e:
            logging.warning(f"Feed {source} failed: {e}")
 
    validated = len(matches) > 0
    return {
        "validated": validated,
        "confidence": "high" if len(matches) >= 2 else "medium" if validated else "low",
        "matched_sources": sorted(matches, key=lambda x: -x["overlap_score"])[:3],
        "message": (
            f"Found in {len(matches)} trusted source(s)." if validated
            else "Not found in trusted feeds. Treat with caution."
        )
    }
 
def fetch_recent_rbi_news(topic: str = "") -> list:
    """
    Fetch recent RBI press releases. Optionally filter by topic keyword.
    """
    try:
        feed = feedparser.parse(TRUSTED_FEEDS["rbi"])
        results = []
        for entry in feed.entries[:15]:
            title = entry.get("title", "")
            if not topic or topic.lower() in title.lower():
                results.append({
                    "title":     title,
                    "link":      entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "summary":   entry.get("summary", "")[:300]
                })
        return results[:5]
    except Exception as e:
        logging.error(f"RBI feed error: {e}")
        return []
 
def fetch_sector_news(sector: str) -> list:
    """
    Fetch recent news for a given sector (IT, banking, manufacturing, etc).
    """
    sector_feeds = {
        "it":            "https://www.livemint.com/rss/technology",
        "banking":       "https://www.thehindu.com/business/Industry/feeder/default.rss",
        "manufacturing": "https://www.thehindu.com/business/Economy/feeder/default.rss",
        "economy":       "https://www.livemint.com/rss/economy",
    }
    url = sector_feeds.get(sector.lower(), sector_feeds["economy"])
    try:
        feed = feedparser.parse(url)
        return [{"title": e.get("title",""), "link": e.get("link","")}
                for e in feed.entries[:5]]
    except Exception as e:
        logging.error(f"Sector feed error: {e}")
        return []
 
def get_rbi_repo_rate_context() -> dict:
    """
    Returns current RBI repo rate context and transmission mechanics.
    Used by Impact Translator for EMI calculations.
    """
    return {
        "current_repo_rate_percent": 6.5,
        "typical_home_loan_spread":  2.25,
        "avg_transmission_months":   3,
        "note": "RBI repo rate as of early 2025. Verify against latest RBI press release.",
        "emi_formula": "EMI = P × r × (1+r)^n / ((1+r)^n - 1) where r=monthly_rate, n=months",
        "emi_delta_approx": "For ₹10L loan, 25bps rate change ≈ ₹75/month EMI change"
    }
