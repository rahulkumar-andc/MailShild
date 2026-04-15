import logging
from datetime import timedelta
from django.utils import timezone
from groq import Groq
from django.conf import settings
from .models import Message, Reminder

logger = logging.getLogger(__name__)

def generate_daily_briefing():
    """
    Gathers messages from the last 24 hours and upcoming deadlines,
    then uses Groq to write a short text briefing.
    """
    if not getattr(settings, 'GROQ_API_KEY', None):
        return "GROQ_API_KEY is not configured. Cannot generate briefing."

    # Data collection
    cutoff = timezone.now() - timedelta(hours=24)
    recent_messages = Message.objects.filter(received_at__gte=cutoff).exclude(category='SPAM')
    
    msg_summary = list(recent_messages.values('source', 'sender', 'category', 'is_phishing'))
    
    upcoming_reminders = Reminder.objects.filter(
        is_sent=False, 
        remind_at__gte=timezone.now(),
        remind_at__lte=timezone.now() + timedelta(days=2)
    ).order_by('remind_at')
    
    rem_summary = [f"{r.title} (Due: {r.remind_at.strftime('%Y-%m-%d %H:%M')})" for r in upcoming_reminders]

    # Context to inject into prompt
    context_str = f"""
--- LAST 24 HOURS MESSAGES ---
Total Non-Spam Messages: {len(msg_summary)}
Categories:
- Important: {sum(1 for m in msg_summary if m['category'] == 'IMPORTANT')}
- Phishing/Threats: {sum(1 for m in msg_summary if m['is_phishing'] or m['category'] == 'THREAT')}
- Deadlines/Academic: {sum(1 for m in msg_summary if m['category'] in ['DEADLINE', 'ACADEMIC'])}

--- UPCOMING DEADLINES (Next 48 Hours) ---
Total: {len(rem_summary)}
{chr(10).join(rem_summary)}
"""

    # 4. Fetch Intelligence Context
    from .intelligence_agent import get_threat_summary_for_briefing
    threat_intel = get_threat_summary_for_briefing()

    # 5. Build prompt
    prompt = f"""You are a smart Personal Security Assistant. 
Generate a concise daily morning briefing in Hinglish.
Focus on:
1. Urgent security threats found in my messages.
2. Important academic/college updates.
3. My upcoming deadlines.
4. General security intelligence from the web.

Context:
{summary_context}

Latest OSINT Intelligence:
{threat_intel}

Rules:
- Speak in a friendly, helpful Hinglish tone.
- Keep it concise.
- Use emojis.
- Start with a friendly greeting like "Here's your summary for the day".
- Highlight only the most important things: Threats, Important emails, and approaching deadlines.
- If there is nothing important, just say "A quiet day! No major threats or deadlines."
- Output pure text (this will be sent via iOS/Android push notification). DO NOT use markdown links, just plain text and emojis.
"""

    client = Groq(api_key=settings.GROQ_API_KEY)
    
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=250
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Briefing generation failed: %s", e)
        return "Failed to generate briefing."
