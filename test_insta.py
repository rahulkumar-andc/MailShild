#!/usr/bin/env python
"""Manually test Instagram connection."""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from analyzer.insta_fetcher import fetch_unseen_dms

print("🔄 Testing Instagram login & fetch...")
print("⚠️ Note: Instagram often blocks unofficial API logins. Be prepared. \n")

dms = fetch_unseen_dms()

if dms:
    print(f"\n✅ SUCCESS! Fetched {len(dms)} DMs from Instagram!")
    for i, dm in enumerate(dms[:5], 1):
        print(f"  [{i}] From: {dm['sender']} | MSG: {dm['body'][:50]}")
else:
    print("\n❌ Failed or found 0 DMs. Check the error above.")
