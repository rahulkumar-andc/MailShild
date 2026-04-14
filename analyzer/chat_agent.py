import logging
from datetime import timedelta
from django.utils import timezone
from groq import Groq
from django.conf import settings
from .models import Message, Reminder

logger = logging.getLogger(__name__)

def generate_context_string():
    """Fetches recent data and formats it into a prompt-friendly context string."""
    # Last 3 days of messages (limit to 100 to avoid token limits)
    cutoff = timezone.now() - timedelta(days=3)
    recent_messages = Message.objects.filter(received_at__gte=cutoff).order_by('-received_at')[:100]
    
    # Upcoming reminders
    upcoming_reminders = Reminder.objects.filter(is_sent=False, remind_at__gte=timezone.now()).order_by('remind_at')[:20]
    
    context_lines = []
    
    if upcoming_reminders.exists():
        context_lines.append("--- UPCOMING REMINDERS/DEADLINES ---")
        for r in upcoming_reminders:
            context_lines.append(f"Reminder: {r.title} | Due: {r.remind_at.strftime('%Y-%m-%d %H:%M:%S')} | Details: {r.description}")
        context_lines.append("")
        
    if recent_messages.exists():
        context_lines.append("--- RECENT MESSAGES (Last 3 Days) ---")
        for m in recent_messages:
            context_lines.append(f"[{m.received_at.strftime('%Y-%m-%d %H:%M:%S')}] From: {m.sender} via {m.source.upper()}")
            context_lines.append(f"Subject/Group: {m.subject}")
            context_lines.append(f"Message: {m.body}")
            context_lines.append(f"Classifier tags: {m.category}, Spammyness: {m.spam_score}")
            context_lines.append("---")
            
    if not context_lines:
        return "No recent messages or upcoming reminders."
        
    return "\n".join(context_lines)

def ask_assistant(user_query):
    """
    Takes a natural language user query and uses Groq to answer it 
    based on the recent Messages and Reminders in the database.
    """
    if not getattr(settings, 'GROQ_API_KEY', None):
        return "GROQ_API_KEY is not configured. Assistant cannot reply."
        
    client = Groq(api_key=settings.GROQ_API_KEY)
    context = generate_context_string()
    
    system_prompt = f"""You are MailShield AI, a highly capable security and organization assistant for a college student/bug bounty hunter.
Your job is to answer the user's questions truthfully and concisely using ONLY the provided context. 
If the user asks a question that cannot be answered using the context, say you don't know based on recent messages.

CONTEXT DATA:
{context}
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query}
            ],
            temperature=0.3,
            max_tokens=500
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Chat agent failed: {e}")
        return f"Error communicating with AI Assistant: {str(e)}"
