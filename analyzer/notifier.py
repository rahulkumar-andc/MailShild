import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def send_notification(source, sender, reason, category, is_phishing):
    """
    Sends a push notification to ntfy.sh
    Title: "New Gmail Alert" or "New Instagram Alert"
    Body: "⚡ IMPORTANT / 🎣 PHISHING — From: sender — reason"
    Priority: urgent for phishing, high for important
    """
    if not settings.NTFY_TOPIC:
        logger.warning("NTFY_TOPIC not configured. Skipping notification.")
        return

    title = f"New {source.capitalize()} Alert"

    if is_phishing:
        prefix = "🎣 PHISHING"
        ntfy_prio = "5"  # urgent
    else:
        prefix = "⚡ IMPORTANT"
        ntfy_prio = "4"  # high

    body = f"{prefix} — From: {sender}\nReason: {reason}"

    url = f"https://ntfy.sh/{settings.NTFY_TOPIC}"
    headers = {
        "Title": title,
        "Priority": ntfy_prio,
        "Tags": "warning" if is_phishing else "zap"
    }

    try:
        requests.post(url, data=body.encode('utf-8'), headers=headers, timeout=10)
        logger.info("Notification sent to topic '%s'.", settings.NTFY_TOPIC)
    except Exception as e:
        logger.error("Failed to send notification: %s", e)
