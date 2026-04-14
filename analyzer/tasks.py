from celery import shared_task
from django.utils import timezone
from .models import Message
from .gmail_fetcher import fetch_unseen_emails
from .insta_fetcher import fetch_unseen_dms
from .ai_classifier import classify_message
from .notifier import send_notification
from django.conf import settings

@shared_task
def scan_gmail():
    if settings.DRY_RUN:
        print("[DRY RUN] Would scan Gmail now.")
        # Uncomment below if you still want to fetch but not classify in dry run
        # return
    
    emails = fetch_unseen_emails()
    for email_data in emails:
        process_message(email_data)

@shared_task
def scan_instagram():
    if settings.DRY_RUN:
        print("[DRY RUN] Would scan Instagram now.")
        # Uncomment below if you still want to fetch but not classify in dry run
        # return
        
    dms = fetch_unseen_dms()
    for dm_data in dms:
        process_message(dm_data)

def process_message(msg_data):
    """
    Checks if message exists by ID. If not, classifies and saves it, 
    and triggers notification if needed.
    """
    msg_id = msg_data["message_id"]
    if Message.objects.filter(message_id=msg_id).exists():
        # Already processed
        return

    # Call Claude AI for classification
    # If DRY_RUN is active, we might skip the API call to save credits if needed.
    # But usually dry run means we just don't notify or change state.
    # Let's assume we want to classify even in dry run unless we explicitly skip above.
    
    classification = classify_message(
        source=msg_data["source"],
        sender=msg_data["sender"],
        subject=msg_data["subject"],
        body=msg_data["body"]
    )

    should_notify = False
    if classification["category"] in ["IMPORTANT", "PHISHING"] or classification["spam_score"] > 75:
        should_notify = True

    # Save to database
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

    # Notify
    if should_notify and not msg_obj.notified:
        if not settings.DRY_RUN:
            send_notification(
                source=msg_obj.source,
                sender=msg_obj.sender,
                reason=msg_obj.reason,
                category=msg_obj.category,
                is_phishing=msg_obj.is_phishing
            )
            msg_obj.notified = True
            msg_obj.save()
        else:
            print(f"[DRY RUN] Would send notification for {msg_obj.source} from {msg_obj.sender}")
