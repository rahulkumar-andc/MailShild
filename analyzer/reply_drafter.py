"""
AI Smart Reply Drafter — Generates context-aware reply drafts using Groq.
Adapts tone based on message category and source.
"""
import logging
from groq import Groq
from django.conf import settings

logger = logging.getLogger(__name__)


TONE_MAP = {
    'COLLEGE': 'formal and respectful, like a student replying to faculty',
    'ACADEMIC': 'formal and respectful academic tone',
    'DEADLINE': 'urgent but polite, acknowledging the deadline',
    'CLASS_UPDATE': 'brief and professional acknowledgment',
    'IMPORTANT': 'professional and concise',
    'COLLAB': 'friendly and enthusiastic, open to collaboration',
    'FAN': 'warm and grateful, thanking the person',
    'PHISHING': 'DO NOT draft a reply. Instead warn the user this is a phishing attempt.',
    'THREAT': 'DO NOT draft a reply. Instead advise the user to report this.',
    'SPAM': 'DO NOT draft a reply. This is spam.',
    'NORMAL': 'casual and friendly',
    'NEWSLETTER': 'brief acknowledgment or no reply needed',
    'PROMOTIONAL': 'brief acknowledgment or no reply needed',
    'FAVOURITE': 'warm and personal, as this is a close contact',
    'CASUAL': 'casual and friendly',
}


def draft_reply(message_obj):
    """
    Generate an AI-drafted reply for a given Message object.
    Returns a string with the draft reply text.
    """
    if not getattr(settings, 'GROQ_API_KEY_CHAT', None):
        return "Error: GROQ_API_KEY_CHAT is not configured."

    category = message_obj.category or 'NORMAL'
    tone = TONE_MAP.get(category, 'professional and concise')

    # Don't draft replies for dangerous categories
    if category in ('PHISHING', 'THREAT', 'SPAM'):
        warnings = {
            'PHISHING': "⚠️ This message is classified as PHISHING. Do NOT reply to it. Report it immediately and block the sender.",
            'THREAT': "🚨 This message is classified as a THREAT. Do NOT engage. Save evidence and report to authorities.",
            'SPAM': "🗑️ This is SPAM. No reply is recommended.",
        }
        return warnings.get(category, "No reply recommended.")

    client = Groq(api_key=settings.GROQ_API_KEY_CHAT)

    # Truncate body to control tokens
    body = message_obj.body[:1500]

    prompt = f"""You are a smart reply assistant for a college student and security researcher.
Draft a professional reply to the following message.

Source: {message_obj.source}
Sender: {message_obj.sender}
Subject: {message_obj.subject or 'N/A'}
Original Message: {body}
Category: {category}

Tone: {tone}

Rules:
1. Keep the reply concise (2-5 sentences max).
2. Be polite and professional.
3. If it's about a deadline, acknowledge the deadline and confirm action.
4. If it's a collaboration request, show interest and ask for details.
5. Do NOT include subject line or "Dear [name]" — just the reply body.
6. Reply in the same language as the original message.

Draft the reply:"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Reply draft failed: %s", e)
        return f"Error generating reply: {str(e)}"
