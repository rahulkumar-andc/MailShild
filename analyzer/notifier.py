import requests
from django.conf import settings

def send_notification(source, sender, reason, category, is_phishing):
    """
    Sends a push notification to ntfy.sh
    Title: "New Gmail Alert" or "New Instagram Alert"
    Body: "⚡ IMPORTANT / 🎣 PHISHING — From: sender — reason"
    Priority: urgent for phishing, high for important
    """
    if not settings.NTFY_TOPIC:
        print("NTFY_TOPIC not configured. Skipping notification.")
        return

    title = f"New {source.capitalize()} Alert"
    
    if is_phishing:
        prefix = "🎣 PHISHING"
        priority_val = "urgent" # ntfy priority 5
        ntfy_prio = "5"
    else:
        prefix = "⚡ IMPORTANT"
        priority_val = "high"   # ntfy priority 4
        ntfy_prio = "4"
        
    body = f"{prefix} — From: {sender}\nReason: {reason}"

    url = f"https://ntfy.sh/{settings.NTFY_TOPIC}"
    headers = {
        "Title": title,
        "Priority": ntfy_prio,
        "Tags": "warning" if is_phishing else "zap"
    }

    try:
        requests.post(url, data=body.encode('utf-8'), headers=headers, timeout=10)
        print(f"Notification sent to {settings.NTFY_TOPIC}")
    except Exception as e:
        print(f"Failed to send notification: {e}")
