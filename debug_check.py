#!/usr/bin/env python
"""Quick debug script to check MailShield status."""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
from analyzer.models import Message

print("=" * 60)
print("MailShield Debug Check")
print("=" * 60)

# 1. Check DRY_RUN
print(f"\n1. DRY_RUN = {settings.DRY_RUN}")
if settings.DRY_RUN:
    print("   ❌ DRY_RUN is True! Celery tasks will SKIP fetching.")
else:
    print("   ✅ DRY_RUN is False. Tasks will fetch messages.")

# 2. Check Gmail credentials
print(f"\n2. GMAIL_USER = {settings.GMAIL_USER}")
print(f"   GMAIL_APP_PASSWORD = {'***' + settings.GMAIL_APP_PASSWORD[-4:] if settings.GMAIL_APP_PASSWORD else 'NOT SET'}")

# 3. Check Groq API key
print(f"\n3. GROQ_API_KEY = {'***' + settings.GROQ_API_KEY[-4:] if settings.GROQ_API_KEY else 'NOT SET'}")

# 4. Check DB
msg_count = Message.objects.count()
print(f"\n4. Total messages in DB: {msg_count}")
if msg_count > 0:
    for m in Message.objects.all().order_by('-received_at')[:5]:
        print(f"   - [{m.source}] {m.sender[:30]} | {m.category} | {m.received_at}")
else:
    print("   ❌ No messages in database yet.")

# 5. Try Gmail fetch manually
print("\n5. Testing Gmail IMAP connection...")
try:
    import imaplib
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(settings.GMAIL_USER, settings.GMAIL_APP_PASSWORD)
    mail.select("inbox")
    status, messages = mail.search(None, "UNSEEN")
    if status == "OK":
        email_ids = messages[0].split() if messages[0] else []
        print(f"   ✅ Gmail login success! Unseen emails: {len(email_ids)}")
    else:
        print(f"   ❌ Gmail search failed: {status}")
    mail.logout()
except Exception as e:
    print(f"   ❌ Gmail connection failed: {e}")

# 6. Check Redis
print("\n6. Testing Redis connection...")
try:
    import redis
    r = redis.from_url(settings.CELERY_BROKER_URL)
    r.ping()
    print(f"   ✅ Redis connected at {settings.CELERY_BROKER_URL}")
except Exception as e:
    print(f"   ❌ Redis failed: {e}")

print("\n" + "=" * 60)
