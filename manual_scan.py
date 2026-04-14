#!/usr/bin/env python
"""Manually trigger a Gmail scan — fetches a few emails, classifies, saves to DB."""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.utils import timezone
from analyzer.gmail_fetcher import fetch_unseen_emails
from analyzer.ai_classifier import classify_message
from analyzer.models import Message

print("🔄 Fetching unseen emails from Gmail...")
emails = fetch_unseen_emails()
print(f"📬 Fetched {len(emails)} unseen emails.")

if not emails:
    print("❌ No unseen emails found.")
    sys.exit(0)

# Process only first 5 for quick test
limit = min(5, len(emails))
print(f"\n🧪 Processing first {limit} emails as test...\n")

for i, email_data in enumerate(emails[:limit], 1):
    msg_id = email_data["message_id"]
    
    if Message.objects.filter(message_id=msg_id).exists():
        print(f"  [{i}] ⏭  Already exists: {email_data['subject'][:50]}")
        continue
    
    print(f"  [{i}] 📧 From: {email_data['sender'][:40]}")
    print(f"       Subject: {email_data['subject'][:50]}")
    
    try:
        classification = classify_message(
            source=email_data["source"],
            sender=email_data["sender"],
            subject=email_data["subject"],
            body=email_data["body"]
        )
        print(f"       🏷  Category: {classification['category']} | Spam: {classification['spam_score']} | Phishing: {classification['is_phishing']}")
        
        should_notify = (
            classification["category"] in ["IMPORTANT", "PHISHING", "THREAT"]
            or classification["spam_score"] > 75
            or classification["is_phishing"]
        )
        
        Message.objects.create(
            source=email_data["source"],
            message_id=msg_id,
            sender=email_data["sender"],
            subject=email_data["subject"],
            body=email_data["body"],
            category=classification["category"],
            spam_score=classification["spam_score"],
            priority=classification["priority"],
            reason=classification["reason"],
            is_phishing=classification["is_phishing"],
            should_notify=should_notify,
            notified=False,
            received_at=email_data["received_at"] or timezone.now()
        )
        print(f"       ✅ Saved to database!")
    except Exception as e:
        print(f"       ❌ Classification failed: {e}")

print(f"\n{'='*60}")
total = Message.objects.count()
print(f"✅ Done! Total messages in DB now: {total}")
print(f"🌐 Refresh your dashboard at http://127.0.0.1:8000/ to see them!")
