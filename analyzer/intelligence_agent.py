import logging
import feedparser
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)

# Selected OSINT Feeds
FEEDS = {
    "The Hacker News": "https://feeds.feedburner.com/TheHackersNews",
    "BleepingComputer": "https://www.bleepingcomputer.com/feed/",
}

def fetch_latest_threats(limit=5):
    """
    Fetches the latest security news and threats from configured RSS feeds.
    Returns a list of dicts.
    """
    threats = []
    
    for source_name, url in FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]: # Take top 3 from each
                threats.append({
                    "source": source_name,
                    "title": entry.title,
                    "link": entry.link,
                    "published": getattr(entry, 'published', 'Recently'),
                    "summary": entry.summary[:200] + "..." if hasattr(entry, 'summary') else ""
                })
        except Exception as e:
            logger.error(f"Failed to fetch feed {source_name}: {e}")
            
    # Sort or filter if needed, here we just return the list
    return threats[:limit]

def get_threat_summary_for_briefing():
    """Formats the latest threats for inclusion in a text briefing."""
    threats = fetch_latest_threats()
    if not threats:
        return "No new major threat intelligence reports in the last 24 hours."
    
    lines = ["--- LATEST SECURITY INTELLIGENCE ---"]
    for t in threats:
        lines.append(f"• [{t['source']}] {t['title']}")
        lines.append(f"  Link: {t['link']}")
    
    return "\n".join(lines)
