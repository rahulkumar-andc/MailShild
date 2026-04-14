import os
import time
import logging
import random
from instagrapi import Client
from django.conf import settings
from django.utils.timezone import make_aware

logger = logging.getLogger(__name__)

# Path to store session settings to minimize login attempts
SESSION_FILE = os.path.join(settings.BASE_DIR, 'insta_session.json')


def _get_client():
    """
    Creates an instagrapi Client with a realistic device fingerprint
    and challenge handler to avoid Instagram IP blocks.
    """
    cl = Client()

    # Set a realistic Samsung device fingerprint (avoids default bot-like signature)
    cl.set_device({
        "app_version": "393.1.0.50.76",
        "android_version": 31,
        "android_release": "12",
        "dpi": "480dpi",
        "resolution": "1080x2400",
        "manufacturer": "samsung",
        "device": "a52q",
        "model": "SM-A525F",
        "cpu": "qcom",
        "version_code": "314070422",
    })

    # Set locale to match a real Indian device
    cl.set_locale("en_IN")
    cl.set_timezone_offset(19800)  # IST = UTC+5:30 = 19800 seconds

    # Set user-agent delay to mimic human behavior
    cl.delay_range = [2, 5]

    # Challenge handler: if Instagram sends a verification challenge,
    # log it clearly so the user knows what to do
    def challenge_handler(username, choice):
        logger.warning(
            "⚠️ Instagram Challenge Required for %s! choice=%s. "
            "Please open Instagram app on your phone, approve the login, "
            "then re-run this script.", username, choice
        )
        # Return empty — this will cause login to fail gracefully
        # The user needs to approve from their phone first
        return ""

    cl.challenge_code_handler = challenge_handler

    return cl


def fetch_unseen_dms():
    """
    Fetches latest Instagram DMs using instagrapi.
    Warning: This is an unofficial API. Frequent calls may result in account blocks.
    To mitigate this, we save the session JSON locally and use realistic device settings.
    """
    if not settings.INSTA_USER or not settings.INSTA_PASSWORD:
        logger.warning("Instagram credentials not configured. Skipping.")
        return []

    cl = _get_client()

    try:
        # Strategy 1: Try reusing saved session first (no fresh login needed)
        if os.path.exists(SESSION_FILE):
            logger.info("Loading saved Instagram session...")
            cl.load_settings(SESSION_FILE)
            cl.login(settings.INSTA_USER, settings.INSTA_PASSWORD)
            try:
                cl.get_timeline_feed()  # Validate session
                logger.info("Instagram session is still valid.")
            except Exception:
                logger.warning("Saved session expired: attempting fresh login...")
                # Delete stale session and fall through to fresh login
                os.remove(SESSION_FILE)
                cl = _get_client()
                _fresh_login(cl)
        else:
            _fresh_login(cl)

    except Exception as e:
        logger.error("Instagram login failed: %s", e)
        # Clean up stale session if it exists
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
        return []

    fetched_dms = []

    try:
        # Small delay before fetching DMs to look more human
        time.sleep(random.uniform(1.5, 3.0))

        # Fetch recent 10 threads — use raw API to avoid Pydantic validation
        # errors on media messages with null video_url
        result = cl.private_request("direct_v2/inbox/", params={
            "visual_message_return_type": "unseen",
            "thread_message_limit": "10",
            "persistentBadging": "true",
            "limit": "10",
            "is_prefetching": "false",
        })

        threads_data = result.get("inbox", {}).get("threads", [])
        for thread in threads_data:
            try:
                items = thread.get("items", [])
                if not items:
                    continue

                last_msg = items[0]
                msg_id = f"ig_{last_msg.get('item_id', 'unknown')}"

                # Get sender user_id
                sender_id = str(last_msg.get("user_id", "unknown_ig_user"))

                # Try to map user_id to actual username
                sender = sender_id
                for u in thread.get("users", []):
                    if str(u.get("pk", "")) == sender_id or str(u.get("id", "")) == sender_id:
                        sender = u.get("username", sender_id)
                        break

                # Extract text from the message
                body = last_msg.get("text", None)
                if not body:
                    item_type = last_msg.get("item_type", "unknown")
                    body = f"[Non-text message: {item_type}]"

                # Parse timestamp (microseconds)
                ts = last_msg.get("timestamp")
                received_at = None
                if ts:
                    from datetime import datetime, timezone as tz
                    # Instagram timestamps are in microseconds
                    received_at = datetime.fromtimestamp(int(ts) / 1_000_000, tz=tz.utc)

                fetched_dms.append({
                    "source": "instagram",
                    "message_id": msg_id,
                    "sender": sender,
                    "subject": "Instagram DM",
                    "body": body,
                    "received_at": received_at,
                })
            except Exception as e:
                logger.warning("Skipping DM thread due to parse error: %s", e)
                continue

    except Exception as e:
        logger.error("Failed to fetch DMs: %s", e)

    logger.info("Fetched %d DMs from Instagram.", len(fetched_dms))
    return fetched_dms


def _fresh_login(cl):
    """Performs a fresh Instagram login with human-like delays."""
    logger.info("Performing fresh Instagram login...")
    # Small pre-login delay to mimic app startup
    time.sleep(random.uniform(2.0, 4.0))
    cl.login(settings.INSTA_USER, settings.INSTA_PASSWORD)
    cl.dump_settings(SESSION_FILE)
    logger.info("Instagram login successful! Session saved.")
