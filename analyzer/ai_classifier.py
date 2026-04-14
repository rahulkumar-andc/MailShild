import json
import logging
from groq import Groq
from django.conf import settings

logger = logging.getLogger(__name__)


def classify_message(source, sender, subject, body):
    """
    Sends the message content to Groq (Llama 3) for classification.
    Returns a dict with classification details.
    For WhatsApp messages, also extracts reminder info if applicable.
    """
    if not getattr(settings, 'GROQ_API_KEY', None):
        logger.warning("Groq API key not configured. Skipping classification.")
        return get_default_classification()

    client = Groq(api_key=settings.GROQ_API_KEY)

    if source == "gmail":
        categories = "IMPORTANT, SPAM, PHISHING, COLLEGE, PROMOTIONAL, NEWSLETTER, NORMAL"
    elif source == "whatsapp":
        categories = "ACADEMIC, DEADLINE, CLASS_UPDATE, IMPORTANT, CASUAL, SPAM"
    else:
        categories = "IMPORTANT, SPAM, COLLAB, FAN, THREAT, NORMAL"

    # Truncate to 1500 chars to avoid hitting the 6000 TPM limit on Groq free tier
    body = body[:1500]

    if source == "whatsapp":
        prompt = f"""You are a smart AI assistant for a college student.
Your task is to analyze a WhatsApp group message and determine if it's academically important.

Group: {subject}
Sender: {sender}
Message: {body}

Categorize the message into exactly ONE of: {categories}.
Categories explained:
- ACADEMIC: General academic info (study material, notes shared, etc.)
- DEADLINE: Has a specific deadline (assignment due, project submission, form filling)
- CLASS_UPDATE: Class timing changes, cancellations, room changes
- IMPORTANT: Non-academic but important (event registration, fee payment, etc.)
- CASUAL: Casual chat, memes, good morning, jokes, random conversation
- SPAM: Forwarded spam, ads, irrelevant

Also determine:
1. spam_score: integer 0-100
2. priority: 'low', 'normal', 'high', or 'urgent'
3. reason: Brief 1-sentence reason
4. is_phishing: true or false
5. reminder: If category is DEADLINE or CLASS_UPDATE or ACADEMIC with a specific date/time,
   extract a reminder object. Otherwise set to null.

Respond ONLY with valid JSON:
{{
    "category": "CATEGORY_NAME",
    "spam_score": 0,
    "priority": "normal",
    "reason": "Because...",
    "is_phishing": false,
    "reminder": {{
        "title": "Short title for the reminder",
        "description": "Full details of what to do",
        "deadline": "YYYY-MM-DDTHH:MM:SS or null if no specific time"
    }}
}}
If no reminder needed, set "reminder": null.
"""
    else:
        prompt = f"""You are a security and organization AI assistant for a college student, bug bounty hunter, and security researcher.
Your task is to classify an incoming {source} message.

Source: {source}
Sender: {sender}
Subject: {subject}
Body: {body}

Categorize the message into exactly ONE of the following categories: {categories}.
Also determine:
1. spam_score: an integer from 0 to 100 (100 being definite spam/malicious).
2. priority: 'low', 'normal', 'high', or 'urgent'.
3. reason: A brief 1-sentence reason for your classification.
4. is_phishing: true or false.

Respond ONLY with a valid JSON object of this structure:
{{
    "category": "CATEGORY_NAME",
    "spam_score": 0,
    "priority": "low",
    "reason": "Because...",
    "is_phishing": false
}}
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=1024,
            response_format={"type": "json_object"}
        )
        result_text = response.choices[0].message.content

        # safely parse JSON out of potential surrounding text
        start_idx = result_text.find('{')
        end_idx = result_text.rindex('}') + 1
        json_str = result_text[start_idx:end_idx]

        data = json.loads(json_str)
        result = {
            "category": data.get("category", "NORMAL"),
            "spam_score": data.get("spam_score", 0),
            "priority": data.get("priority", "normal"),
            "reason": data.get("reason", ""),
            "is_phishing": bool(data.get("is_phishing", False)),
        }

        # Extract reminder for WhatsApp messages
        if source == "whatsapp" and data.get("reminder"):
            result["reminder"] = data["reminder"]

        return result

    except Exception as e:
        logger.error("Classification failed: %s", e)
        raise  # FIX 11: Re-raise so Celery's autoretry can catch it


def get_default_classification():
    return {
        "category": "NORMAL",
        "spam_score": 0,
        "priority": "normal",
        "reason": "Classification failed or API key missing.",
        "is_phishing": False
    }

