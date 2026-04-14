#!/usr/bin/env python
"""Quick test to send a ntfy notification."""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from analyzer.notifier import send_notification

print("📤 Sending test notification to ntfy...")
send_notification(
    source="gmail",
    sender="test@example.com",
    reason="This is a TEST notification from MailShield AI! If you see this, ntfy is working perfectly. 🎉",
    category="IMPORTANT",
    is_phishing=False
)
print("✅ Sent! Check your ntfy app on phone.")
