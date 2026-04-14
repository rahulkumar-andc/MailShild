#!/usr/bin/env python
"""
One-time interactive Instagram login script.
This handles the email/SMS challenge verification code.
After successful login, session is saved and Celery can reuse it.
"""
import os
import sys
import time
import random
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from instagrapi import Client
from django.conf import settings

SESSION_FILE = os.path.join(settings.BASE_DIR, 'insta_session.json')


def challenge_code_handler(username, choice):
    """Interactively ask user for the verification code."""
    print(f"\n🔐 Instagram ne verification code bheja hai via: {choice}")
    print(f"   Account: {username}")
    print(f"   Apna email/SMS check karo aur code enter karo:\n")
    code = input("   Enter code: ").strip()
    return code


def main():
    print("=" * 60)
    print("🔑 Instagram One-Time Login Setup")
    print("=" * 60)

    if not settings.INSTA_USER or not settings.INSTA_PASSWORD:
        print("❌ INSTA_USER / INSTA_PASSWORD not set in .env")
        sys.exit(1)

    # Remove old session
    if os.path.exists(SESSION_FILE):
        os.remove(SESSION_FILE)
        print("🗑️  Old session removed.")

    cl = Client()

    # Set realistic device
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
    cl.set_locale("en_IN")
    cl.set_timezone_offset(19800)
    cl.delay_range = [2, 5]

    # Set interactive challenge handler
    cl.challenge_code_handler = challenge_code_handler

    print(f"\n🔄 Logging in as {settings.INSTA_USER}...")
    time.sleep(random.uniform(2.0, 4.0))

    try:
        cl.login(settings.INSTA_USER, settings.INSTA_PASSWORD)
        cl.dump_settings(SESSION_FILE)
        print(f"\n✅ Login SUCCESSFUL! Session saved to {SESSION_FILE}")
        print("   Ab Celery worker is session ko reuse karega — dobara login nahi karna padega!")

        # Quick test
        print("\n🧪 Testing DM fetch...")
        time.sleep(random.uniform(1.5, 3.0))
        result = cl.private_request("direct_v2/inbox/", params={
            "visual_message_return_type": "unseen",
            "thread_message_limit": "10",
            "persistentBadging": "true",
            "limit": "5",
            "is_prefetching": "false",
        })
        threads = result.get("inbox", {}).get("threads", [])
        print(f"   ✅ Fetched {len(threads)} DM threads!")
        for t in threads[:5]:
            items = t.get("items", [])
            if items:
                body = (items[0].get("text") or "[media]")[:50]
                print(f"      - {body}")

    except Exception as e:
        print(f"\n❌ Login failed: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("✅ Done! Ab Celery worker restart karo aur Instagram DMs auto-fetch honge.")
    print("=" * 60)


if __name__ == "__main__":
    main()
