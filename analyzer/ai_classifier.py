import json
import logging
import anthropic
from django.conf import settings

logger = logging.getLogger(__name__)


def classify_message(source, sender, subject, body):
    """
    Sends the message content to Claude for classification.
    Returns a dict with classification details.
    """
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("Anthropic API key not configured. Skipping classification.")
        return get_default_classification()

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    if source == "gmail":
        categories = "IMPORTANT, SPAM, PHISHING, COLLEGE, PROMOTIONAL, NEWSLETTER, NORMAL"
    else:
        categories = "IMPORTANT, SPAM, COLLAB, FAN, THREAT, NORMAL"

    body = body[:3000]

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
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            temperature=0.0,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        result_text = response.content[0].text

        # safely parse JSON out of potential surrounding text
        start_idx = result_text.find('{')
        end_idx = result_text.rindex('}') + 1
        json_str = result_text[start_idx:end_idx]

        data = json.loads(json_str)
        return {
            "category": data.get("category", "NORMAL"),
            "spam_score": data.get("spam_score", 0),
            "priority": data.get("priority", "normal"),
            "reason": data.get("reason", ""),
            "is_phishing": bool(data.get("is_phishing", False))
        }

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
