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

# Path to store username-to-id mapping to avoid redundant GQL lookups
USER_ID_CACHE_FILE = os.path.join(settings.BASE_DIR, 'insta_user_id_cache.json')


# Path to flag if Instagram login is blocked by a challenge
# If this file exists, automated tasks will skip Instagram calls
INSTA_CHALLENGE_FLAG = os.path.join(settings.BASE_DIR, 'insta_challenge_required.flag')


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
    # log it clearly and stop automated attempts.
    def challenge_handler(username, choice):
        logger.warning(
            "⚠️ Instagram Challenge Required for %s! choice=%s. "
            "Automated scans PAUSED to avoid account ban.", username, choice
        )
        # Create a flag file to block further automated attempts
        try:
            with open(INSTA_CHALLENGE_FLAG, 'w') as f:
                f.write(f"Challenge: {choice} at {time.ctime()}")
        except Exception as e:
            logger.error("Failed to create challenge flag: %s", e)

        # Raise exception to break the login process immediately
        # Returning empty string causes instagrapi to try verifying with blank code
        raise Exception(f"Instagram Challenge Required ({choice}). Please solve manually.")

    cl.challenge_code_handler = challenge_handler

    return cl


def _load_user_id_cache():
    """Loads username-to-id mapping from local JSON cache."""
    if os.path.exists(USER_ID_CACHE_FILE):
        try:
            import json
            with open(USER_ID_CACHE_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load user ID cache: %s", e)
    return {}


def _save_user_id_cache(cache):
    """Saves username-to-id mapping to local JSON cache."""
    try:
        import json
        with open(USER_ID_CACHE_FILE, 'w') as f:
            json.dump(cache, f)
    except Exception as e:
        logger.warning("Failed to save user ID cache: %s", e)


def safe_api_call(func, *args, **kwargs):
    """
    Wrapper for Instagram API calls that catches 429 Errors
    and implements exponential backoff.
    """
    retries = 3
    base_delay = 5
    for i in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_msg = str(e).lower()
            if "429" in error_msg or "too many requests" in error_msg:
                wait_time = base_delay * (2 ** i) + random.uniform(1, 5)
                logger.warning(f"⚠️ Instagram Rate Limit (429)! Retrying in {wait_time:.1f}s... (Attempt {i+1}/{retries})")
                time.sleep(wait_time)
            else:
                raise e
    return func(*args, **kwargs)  # Final attempt


def fetch_unseen_dms():
    """
    Fetches latest Instagram DMs using instagrapi.
    Warning: This is an unofficial API. Frequent calls may result in account blocks.
    To mitigate this, we save the session JSON locally and use realistic device settings.
    """
    if os.path.exists(INSTA_CHALLENGE_FLAG):
        logger.warning("Instagram scan skipped: Security challenge flag exists. Please run insta_login.py manually.")
        return []

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

        # Fetch recent 20 threads — fetch ALL, not just unseen
        # This ensures birthday wishes are captured even if user saw them on phone
        result = safe_api_call(cl.private_request, "direct_v2/inbox/", params={
            "thread_message_limit": "10",
            "persistentBadging": "true",
            "limit": "20",
            "is_prefetching": "false",
        })

        threads_data = result.get("inbox", {}).get("threads", [])
        
        # Also fetch pending requests (birthday wishes from non-followers)
        try:
            time.sleep(random.uniform(1.0, 2.0))
            pending = safe_api_call(cl.private_request, "direct_v2/pending_inbox/", params={
                "thread_message_limit": "5",
                "limit": "10",
            })
            pending_threads = pending.get("inbox", {}).get("threads", [])
            threads_data.extend(pending_threads)
        except Exception as e:
            logger.warning("Could not fetch pending inbox: %s", e)

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

                # Extract text — handle story mentions/shares specially
                item_type = last_msg.get("item_type", "unknown")
                body = last_msg.get("text", None)
                
                if item_type in ("story_share", "reel_share", "felix_share"):
                    # Story mention or share — extract any text and tag it
                    story_text = body or ""
                    story_media = last_msg.get("story_share", {})
                    if story_media and story_media.get("message"):
                        story_text = story_media.get("message", "")
                    if not story_text:
                        story_text = f"[Story mention from {sender}]"
                    body = f"[Story mention] {story_text}"
                elif not body:
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
                    "sender_id": sender_id,  # Include the numeric ID
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


def check_insta_status():
    """
    Diagnostic: Check if Instagram login/session is working.
    Returns a status string for the AI assistant.
    """
    if os.path.exists(INSTA_CHALLENGE_FLAG):
        return "⚠️ Instagram is BLOCKED by a security challenge. Please run `python3 insta_login.py` to solve it."

    if not settings.INSTA_USER or not settings.INSTA_PASSWORD:
        return "❌ Instagram credentials not configured in .env file."
    
    session_exists = os.path.exists(SESSION_FILE)
    
    cl = _get_client()
    try:
        if session_exists:
            cl.load_settings(SESSION_FILE)
            cl.login(settings.INSTA_USER, settings.INSTA_PASSWORD)
            cl.get_timeline_feed()
            return f"✅ Instagram connected as @{settings.INSTA_USER}. Session is valid."
        else:
            _fresh_login(cl)
            return f"✅ Fresh Instagram login successful as @{settings.INSTA_USER}."
    except Exception as e:
        error_msg = str(e)
        if 'challenge' in error_msg.lower():
            return (f"⚠️ Instagram login needs verification! Open Instagram app on your phone, "
                    f"approve the suspicious login, then try again. Error: {error_msg}")
        return f"❌ Instagram login failed: {error_msg}"


def send_instagram_dm(username, message, user_id=None):
    """
    Send a DM to an Instagram user.
    ⚠️ SAFETY: Instagram aggressively blocks automated DMs.
    Use sparingly. All messages are tagged with [MailShield AI].
    """
    if os.path.exists(INSTA_CHALLENGE_FLAG):
        return "❌ Cannot send DM: Instagram account is currently in 'Challenge Required' state. Please verify manually."

    if not settings.INSTA_USER or not settings.INSTA_PASSWORD:
        return "Error: Instagram credentials not configured."
    
    # Send message as-is, no AI tag
    tagged_message = message
    
    cl = _get_client()
    try:
        # Login
        if os.path.exists(SESSION_FILE):
            cl.load_settings(SESSION_FILE)
            cl.login(settings.INSTA_USER, settings.INSTA_PASSWORD)
            try:
                # Use a safer call than get_timeline_feed to validate session
                safe_api_call(cl.get_timeline_feed)
            except Exception:
                if os.path.exists(SESSION_FILE):
                    os.remove(SESSION_FILE)
                cl = _get_client()
                _fresh_login(cl)
        else:
            _fresh_login(cl)
        
        # Resolve username to user_id if not provided
        if not user_id:
            # Check local cache first
            cache = _load_user_id_cache()
            if username in cache:
                user_id = cache[username]
                logger.info(f"Using cached user ID for @{username}: {user_id}")
            else:
                logger.info(f"Resolving user ID for @{username}...")
                time.sleep(random.uniform(1.0, 2.5))
                user_id = safe_api_call(cl.user_id_from_username, username)
                # Update cache
                cache[username] = user_id
                _save_user_id_cache(cache)
        
        # Send DM
        time.sleep(random.uniform(1.5, 3.0))
        # Wrap the send in safe_api_call as well
        safe_api_call(cl.direct_send, tagged_message, user_ids=[user_id])
        
        logger.info(f"Instagram DM sent to @{username} (ID: {user_id})")
        return f"✅ Message sent to @{username} on Instagram!"
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to send Instagram DM: {error_msg}")
        if 'challenge' in error_msg.lower():
            return ("⚠️ Instagram needs phone verification before sending DMs. "
                    "Please approve the login from your phone first.")
        if '429' in error_msg:
            return "❌ Failed to send DM: Rate limit exceeded (429). Try again later."
        return f"❌ Failed to send DM: {error_msg}"
