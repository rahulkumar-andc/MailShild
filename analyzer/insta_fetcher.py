import os
from instagrapi import Client
from django.conf import settings
from django.utils.timezone import make_aware
from datetime import datetime

# Path to store session settings to minimize login attempts
SESSION_FILE = os.path.join(settings.BASE_DIR, 'insta_session.json')

def fetch_unseen_dms():
    """
    Fetches latest Instagram DMs using instagrapi.
    Warning: This is an unofficial API. Frequent calls may result in account blocks.
    To mitigate this, we save the session JSON locally.
    """
    if not settings.INSTA_USER or not settings.INSTA_PASSWORD:
        print("Instagram credentials not configured. Skipping.")
        return []

    cl = Client()
    try:
        if os.path.exists(SESSION_FILE):
            cl.load_settings(SESSION_FILE)
            cl.login(settings.INSTA_USER, settings.INSTA_PASSWORD)
            cl.get_timeline_feed()  # Check if session is valid
        else:
            cl.login(settings.INSTA_USER, settings.INSTA_PASSWORD)
            cl.dump_settings(SESSION_FILE)
    except Exception as e:
        print(f"Instagram login failed: {e}")
        return []

    fetched_dms = []

    try:
        # Fetch recent 10 threads
        threads = cl.direct_threads(amount=10)
        for thread in threads:
            if thread.messages:
                last_msg = thread.messages[0]
                
                # Simple deduplication: we only process messages that are fairly recent (let's say we check if we already have it in DB during save, so here we just return the latest)
                # But to avoid returning too many, we'll just return the single most recent message per thread for checking.
                # A robust system would fetch since last checked, but instagrapi limits exact pagination without lots of API calls.
                
                msg_id = f"ig_{last_msg.id}"
                sender = str(last_msg.user_id) if last_msg.user_id else "unknown_ig_user"
                body = last_msg.text if last_msg.text else "[Non-text message / media]"
                received_at = last_msg.timestamp
                
                # Make timezone aware
                if received_at and received_at.tzinfo is None:
                    received_at = make_aware(received_at)
                
                fetched_dms.append({
                    "source": "instagram",
                    "message_id": msg_id,
                    "sender": sender,
                    "subject": "Instagram DM",
                    "body": body,
                    "received_at": received_at,
                })
    except Exception as e:
        print(f"Failed to fetch DMs: {e}")

    return fetched_dms
