import logging
from celery import shared_task
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from .models import Message, FavouriteUser, Reminder
from .gmail_fetcher import fetch_unseen_emails
from .insta_fetcher import fetch_unseen_dms
from .ai_classifier import classify_message
from .notifier import send_notification

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=0)
def scan_gmail(self):
    """Fetch and process unseen Gmail messages."""
    if settings.DRY_RUN:
        logger.info("[DRY RUN] Skipping Gmail scan.")
        return

    emails = fetch_unseen_emails()
    for email_data in emails:
        # FIX 10: Dispatch each message as its own Celery task for parallel processing
        process_message_task.delay(email_data)


@shared_task(bind=True, max_retries=0)
def scan_instagram(self):
    """Fetch and process unseen Instagram DMs."""
    if settings.DRY_RUN:
        logger.info("[DRY RUN] Skipping Instagram scan.")
        return

    dms = fetch_unseen_dms()
    for dm_data in dms:
        # FIX 10: Dispatch each message as its own Celery task for parallel processing
        process_message_task.delay(dm_data)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=30, max_retries=3,
             retry_jitter=True, rate_limit="10/m")
def process_message_task(self, msg_data):
    """
    Celery task wrapper around process_message.
    Auto-retries up to 3 times with exponential backoff.
    """
    process_message(msg_data)


def process_message(msg_data):
    """
    Checks if message exists by ID. If not, classifies and saves it,
    and triggers notification if needed.
    For WhatsApp messages, also creates reminders if AI detects deadlines.
    """
    msg_id = msg_data["message_id"]
    if Message.objects.filter(message_id=msg_id).exists():
        logger.debug("Message %s already processed. Skipping.", msg_id)
        return

    # Check for favourite user text message bypass
    is_fav = FavouriteUser.objects.filter(username=msg_data["sender"]).exists()
    is_text = not msg_data["body"].startswith("[Non-text message")

    if is_fav and is_text:
        logger.info("Bypassing AI classification for Favourite User text message: %s", msg_data["sender"])
        classification = {
            "category": "FAVOURITE",
            "spam_score": 0,
            "priority": "high",
            "reason": "Direct text message from Favourite User",
            "is_phishing": False,
        }
    else:
        classification = classify_message(
            source=msg_data["source"],
            sender=msg_data["sender"],
            subject=msg_data["subject"],
            body=msg_data["body"]
        )

    # Determine if notification is needed
    should_notify = False
    notify_categories = [
        "IMPORTANT", "PHISHING", "THREAT", "FAVOURITE",
        "ACADEMIC", "DEADLINE", "CLASS_UPDATE",  # WhatsApp academic categories
    ]
    if (classification["category"] in notify_categories
            or classification["spam_score"] > 75
            or classification["is_phishing"]):
        should_notify = True

    msg_obj = Message.objects.create(
        source=msg_data["source"],
        message_id=msg_id,
        sender=msg_data["sender"],
        subject=msg_data["subject"],
        body=msg_data["body"],
        category=classification["category"],
        spam_score=classification["spam_score"],
        priority=classification["priority"],
        reason=classification["reason"],
        is_phishing=classification["is_phishing"],
        should_notify=should_notify,
        notified=False,
        received_at=msg_data["received_at"] or timezone.now()
    )

    # Send immediate notification for important messages
    if should_notify and not msg_obj.notified:
        send_notification(
            source=msg_obj.source,
            sender=msg_obj.sender,
            reason=msg_obj.reason,
            category=msg_obj.category,
            is_phishing=msg_obj.is_phishing
        )
        msg_obj.notified = True
        msg_obj.save()
        logger.info("Notification sent for %s message from %s", msg_obj.source, msg_obj.sender)

    # Create reminder if AI extracted one (WhatsApp messages)
    reminder_data = classification.get("reminder")
    if reminder_data and isinstance(reminder_data, dict):
        _create_reminder(msg_obj, reminder_data)


def _create_reminder(msg_obj, reminder_data):
    """Creates a Reminder from AI-extracted deadline data."""
    from dateutil import parser as dateutil_parser

    title = reminder_data.get("title", "Reminder")
    description = reminder_data.get("description", "")
    deadline_str = reminder_data.get("deadline")

    if not deadline_str or deadline_str == "null":
        logger.info("No deadline in reminder data; skipping reminder creation.")
        return

    try:
        remind_at = dateutil_parser.parse(deadline_str)
        # Make timezone aware if naive
        if remind_at.tzinfo is None:
            remind_at = timezone.make_aware(remind_at)

        # Don't create reminders for past deadlines
        if remind_at <= timezone.now():
            logger.info("Deadline is in the past; skipping reminder.")
            return

        Reminder.objects.create(
            message=msg_obj,
            title=title,
            description=description,
            remind_at=remind_at,
            is_sent=False,
        )
        logger.info("Reminder created: '%s' at %s", title, remind_at)

    except (ValueError, TypeError) as e:
        logger.warning("Could not parse deadline '%s': %s", deadline_str, e)


@shared_task(bind=True, max_retries=0)
def check_reminders(self):
    """
    Runs every 60 seconds via Celery Beat.
    Sends ntfy notification for any reminders that are due.
    """
    now = timezone.now()
    due_reminders = Reminder.objects.filter(remind_at__lte=now, is_sent=False)

    for reminder in due_reminders:
        try:
            send_notification(
                source="whatsapp",
                sender=f"⏰ Reminder",
                reason=f"{reminder.title}\n{reminder.description}",
                category="REMINDER",
                is_phishing=False,
            )
            reminder.is_sent = True
            reminder.save()
            logger.info("Reminder notification sent: %s", reminder.title)
        except Exception as e:
            logger.error("Failed to send reminder notification: %s", e)


@shared_task(bind=True, max_retries=0)
def clean_old_spam(self):
    """
    Deletes messages categorized as SPAM that are older than 2 days.
    """
    cutoff = timezone.now() - timedelta(days=2)
    old_spam = Message.objects.filter(category='SPAM', received_at__lt=cutoff)
    
    count = old_spam.count()
    if count > 0:
        deleted_count, _ = old_spam.delete()
        logger.info(f"Auto-deleted {deleted_count} SPAM messages older than 2 days.")
    else:
        logger.info("No old SPAM messages found to delete.")
