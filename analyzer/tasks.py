import logging
from celery import shared_task
from django.utils import timezone
from django.conf import settings
from .models import Message
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
             retry_jitter=True)
def process_message_task(self, msg_data):
    """
    Celery task wrapper around process_message.
    FIX 10: Each message runs as its own task (parallel).
    FIX 11: Auto-retries up to 3 times with exponential backoff on any exception
            (covers AI API failures, network errors, etc.).
    """
    process_message(msg_data)


def process_message(msg_data):
    """
    Checks if message exists by ID. If not, classifies and saves it,
    and triggers notification if needed.
    """
    msg_id = msg_data["message_id"]
    if Message.objects.filter(message_id=msg_id).exists():
        logger.debug("Message %s already processed. Skipping.", msg_id)
        return

    classification = classify_message(
        source=msg_data["source"],
        sender=msg_data["sender"],
        subject=msg_data["subject"],
        body=msg_data["body"]
    )

    # FIX 2: Also check is_phishing directly — Claude may mark is_phishing=True
    # with a category other than "PHISHING" (e.g. "NORMAL" with suspicious links)
    should_notify = False
    if (classification["category"] in ["IMPORTANT", "PHISHING", "THREAT"]
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
