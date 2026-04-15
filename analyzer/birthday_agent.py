"""
Birthday Auto-Reply Agent for MailShield AI
============================================
Automatically replies to birthday wishes with personalized AI-generated
thank-you messages across WhatsApp and Instagram.

Safety:
  - All outbound messages are tagged with a signature
  - Rate-limited to prevent spam bans
  - Only activates on the configured birthday date
"""

import logging
import json
import random
import time
from datetime import date
from django.conf import settings
from django.utils import timezone
from groq import Groq

from .models import Message

logger = logging.getLogger(__name__)

# Birthday keywords to detect wishes
BIRTHDAY_KEYWORDS = [
    "happy birthday", "hbd", "bday", "janamdin", "janmdin",
    "birthday mubarak", "b'day", "happybirthday", "happy bday",
    "many many happy returns", "wish you", "🎂", "🎉", "🎁",
    "birthday bhai", "happy b day", "bde", "saalgirah",
    "happy wala birthday", "happiest birthday",
]

# Special contacts — get warmer, more personal replies
# Format: "username": {"type": "crush/bestfriend/family", "notes": "context for AI"}
SPECIAL_CONTACTS = {
    "deeksha_yadv_": {
        "type": "crush",
        "notes": "She is very special. NEVER use sis/sister/bhen/sibling. Reply sweet and personal.",
    },
}

# Track replied message IDs to avoid duplicates (in-memory + DB field)
_replied_cache = set()


def is_birthday_wish(message_body):
    """Check if a message is a birthday wish."""
    if not message_body:
        return False
    body_lower = message_body.lower()
    return any(kw in body_lower for kw in BIRTHDAY_KEYWORDS)


def is_story_mention(message_body):
    """Check if a message is an Instagram story mention/reply."""
    if not message_body:
        return False
    body_lower = message_body.lower()
    return any(kw in body_lower for kw in [
        "[story mention]",
        "mentioned you",
        "story",
        "replied to your story",
        "story_share",
        "reel_share",
        "felix_share",
    ])



def generate_thankyou(sender_name, message_body, source):
    """
    Generate a short, casual thank-you reply.
    Special contacts get warmer, more personal replies.
    """
    api_key = getattr(settings, 'GROQ_API_KEY_CHAT', None) or getattr(settings, 'GROQ_API_KEY', None)
    
    # Check if this is a special contact
    special = SPECIAL_CONTACTS.get(sender_name)
    
    if not api_key:
        if special and special["type"] == "crush":
            return random.choice(_get_special_fallbacks())
        return random.choice(_get_casual_fallbacks())

    try:
        client = Groq(api_key=api_key)
        
        # Build prompt based on contact type
        if special:
            system_prompt = (
                "You are replying to a birthday wish from someone VERY SPECIAL. "
                "Write a SHORT, sweet, personal thank-you. MAX 1 line. "
                f"Context: {special['notes']} "
                "Style examples: 'Thank youu! 🥰✨', 'Aww thanks! Made my day 😊❤️', "
                "'Thankyou so much! ✨🥰'. "
                "STRICT RULES: "
                "- NEVER say sis, sister, bhen, sibling, bro, buddy, yaar, bhai. "
                "- Keep it sweet, personal, and warm. "
                "- Under 10 words. 1-2 emojis. "
                "- Sound genuine and real, not AI. "
                "- Output ONLY the reply text."
            )
        else:
            system_prompt = (
                "You are replying to a birthday wish on behalf of someone. "
                "Write a VERY SHORT and CASUAL thank-you. MAX 1 line. "
                "Style examples: 'Thanks buddy! 🙌', 'Thanks bro! Means a lot 😊', "
                "'Thank you yaar! ❤️', 'Thanks a lot! Glad you remembered 😄'. "
                "RULES: "
                "- Keep it under 10 words. "
                "- Sound like a real person, NOT an AI. "
                "- Use 1-2 emojis max. "
                "- NO formal language, NO 'aapka', NO long sentences. "
                "- Each reply must be slightly different. "
                "- Output ONLY the reply text, nothing else."
            )

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Reply to birthday wish from {sender_name}: \"{message_body}\""}
            ],
            max_tokens=40,
            temperature=1.0,
        )
        reply = response.choices[0].message.content.strip()
        reply = reply.strip('"').strip("'")
        return reply

    except Exception as e:
        logger.error(f"AI thank-you generation failed: {e}")
        if special and special["type"] == "crush":
            return random.choice(_get_special_fallbacks())
        return random.choice(_get_casual_fallbacks())


def _get_special_fallbacks():
    """Sweet, personal fallback replies for special contacts."""
    return [
        "Thank youu! 🥰✨",
        "Aww thanks! Made my day ❤️",
        "Thankyou so much! ✨😊",
        "That's so sweet, thank you! 🥰",
        "Thanks! Really means a lot ❤️✨",
    ]



def _get_casual_fallbacks():
    """Casual, short fallback replies."""
    return [
        "Thanks buddy! 🙌",
        "Thanks a lot! Glad you remembered 😄",
        "Thanks bro! 🎉",
        "Thanks yaar! Means a lot 😊",
        "Thank you so much! ❤️",
        "Thankyou! 🥰",
        "Thanks a lot bro! 🙏",
        "Thank you buddy! 😄🎉",
    ]



def send_birthday_reply(sender, source, reply_text, external_id=None):
    """Send the thank-you reply via the appropriate platform."""

    if source == "whatsapp":
        try:
            import requests
            bridge_secret = getattr(settings, 'WA_BRIDGE_SECRET', '')
            response = requests.post(
                "http://127.0.0.1:3001/send",
                json={
                    "jid": sender,  # sender is already the JID for WhatsApp
                    "message": reply_text,
                    "secret": bridge_secret,
                },
                timeout=15
            )
            if response.status_code == 200:
                logger.info(f"Birthday reply sent to {sender} on WhatsApp")
                return True
            else:
                logger.error(f"WhatsApp reply failed: {response.text}")
                return False
        except Exception as e:
            logger.error(f"WhatsApp send error: {e}")
            return False

    elif source == "instagram":
        try:
            from .insta_fetcher import send_instagram_dm
            result = send_instagram_dm(sender, reply_text, user_id=external_id)
            if "✅" in result:
                logger.info(f"Birthday reply sent to @{sender} on Instagram")
                return True
            else:
                logger.warning(f"Instagram reply issue: {result}")
                return False
        except Exception as e:
            logger.error(f"Instagram send error: {e}")
            return False

    else:
        # Gmail — we don't auto-reply to emails for safety
        logger.info(f"Skipping auto-reply for {source} message from {sender}")
        return False


def process_birthday_wishes(birthday_date=None):
    """
    Main function: Scan recent messages for birthday wishes and auto-reply.
    Only activates on the birthday date (default: April 16).

    Returns: dict with counts of processed/replied messages
    """
    if birthday_date is None:
        birthday_date = date(2026, 4, 16)


    today = timezone.now().date()
    if today != birthday_date:
        logger.debug("Not birthday today (%s). Skipping.", today)
        return {"status": "not_birthday", "date": str(today)}

    logger.info("🎂 BIRTHDAY MODE ACTIVE! Scanning for birthday wishes...")

    # Get messages from last 24 hours that haven't been auto-replied
    # Using 24h window instead of just today to catch wishes from last night
    from datetime import timedelta
    scan_start = timezone.now() - timedelta(hours=24)
    recent_messages = Message.objects.filter(
        received_at__gte=scan_start,
        auto_replied=False,
    ).exclude(
        sender=getattr(settings, 'INSTA_USER', ''),  # Don't reply to self
    ).order_by('-received_at')

    logger.info(f"🔍 Found {recent_messages.count()} unreplied messages in last 24h")
    
    # Debug: show what sources we have
    for msg in recent_messages[:5]:
        is_wish = is_birthday_wish(msg.body)
        is_story = is_story_mention(msg.body)
        logger.info(f"   [{msg.source}] {msg.sender}: '{msg.body[:40]}...' wish={is_wish} story={is_story}")

    stats = {"total_found": 0, "wishes_detected": 0, "replies_sent": 0, "errors": 0}
    
    # Anti-ban: Daily cap — Instagram flags accounts sending too many DMs
    DAILY_CAP = 50
    BATCH_SIZE = 5  # Send 5 replies, then cooldown
    BATCH_COOLDOWN = 30  # 30 second break between batches
    
    # Check how many we've already sent today
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    already_sent = Message.objects.filter(
        auto_replied=True,
        received_at__gte=today_start,
    ).count()
    
    remaining_quota = DAILY_CAP - already_sent
    if remaining_quota <= 0:
        logger.warning(f"🛑 Daily cap reached ({DAILY_CAP} replies). Stopping to protect account.")
        return {"status": "daily_cap_reached", "sent_today": already_sent}
    
    logger.info(f"📊 Quota: {already_sent}/{DAILY_CAP} sent today, {remaining_quota} remaining")
    
    batch_count = 0  # Track messages in current batch

    for msg in recent_messages:
        stats["total_found"] += 1
        
        # Stop if we hit daily cap
        if stats["replies_sent"] >= remaining_quota:
            logger.warning(f"🛑 Daily cap reached mid-scan. Stopping.")
            break

        # Skip if already replied (in-memory cache)
        if msg.message_id in _replied_cache:
            continue

        # Check if it's a birthday wish or story mention
        if is_birthday_wish(msg.body) or is_story_mention(msg.body):
            stats["wishes_detected"] += 1
            logger.info(f"🎉 Birthday wish from {msg.sender} ({msg.source}): {msg.body[:50]}...")

            # Generate personalized reply
            reply = generate_thankyou(msg.sender, msg.body, msg.source)
            logger.info(f"Generated reply for {msg.sender}: {reply[:80]}...")

            # Quick delay — just enough to seem human (1-2s)
            time.sleep(random.uniform(1.0, 2.0))

            # Send reply
            success = send_birthday_reply(msg.sender, msg.source, reply, external_id=msg.sender_external_id)

            if success:
                stats["replies_sent"] += 1
                batch_count += 1
                msg.auto_replied = True
                msg.ai_reply_draft = reply
                msg.save(update_fields=['auto_replied', 'ai_reply_draft'])
                _replied_cache.add(msg.message_id)
                
                # Anti-ban batch processing: after every BATCH_SIZE, take a break
                if batch_count >= BATCH_SIZE:
                    logger.info(f"⏸️ Batch of {BATCH_SIZE} sent. Cooling down {BATCH_COOLDOWN}s...")
                    time.sleep(BATCH_COOLDOWN)
                    batch_count = 0
                else:
                    # Small gap between individual messages (1-3s)
                    time.sleep(random.uniform(1.0, 3.0))
            else:
                stats["errors"] += 1
                # On error, wait a bit longer to avoid hammering
                time.sleep(random.uniform(3.0, 5.0))

    logger.info(f"🎂 Birthday scan complete: {stats}")
    return stats

