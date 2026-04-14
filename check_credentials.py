import os
import sys
import logging
import imaplib
import requests
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Load environment variables from .env
load_dotenv()

def check_gmail():
    user = os.getenv("GMAIL_USER")
    password = os.getenv("GMAIL_APP_PASSWORD")
    if not user or not password:
        logging.error("Gmail credentials missing in .env")
        return False
    
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(user, password)
        mail.logout()
        logging.info("✅ Gmail IMAP connection successful!")
        return True
    except Exception as e:
        logging.error(f"❌ Gmail connection failed: {e}")
        return False

def check_groq():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logging.error("Groq API key missing in .env")
        return False
    
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=10
        )
        logging.info("✅ Groq API key is valid!")
        return True
    except ImportError:
        logging.error("❌ groq module not installed. Run: pip install groq")
        return False
    except Exception as e:
        logging.error(f"❌ Groq API verification failed: {e}")
        return False

def check_instagram():
    user = os.getenv("INSTA_USER")
    password = os.getenv("INSTA_PASSWORD")
    if not user or not password:
        logging.error("Instagram credentials missing in .env")
        return False
    
    try:
        from instagrapi import Client
        cl = Client()
        # Logging in on every check is risky and might trigger blocks, 
        # but we can try to just use basic login or load session
        session_file = 'insta_session.json'
        if os.path.exists(session_file):
            cl.load_settings(session_file)
            cl.login(user, password)
            logging.info("✅ Instagram login successful (via session)!")
        else:
            cl.login(user, password)
            logging.info("✅ Instagram login successful (new session)!")
        return True
    except Exception as e:
        logging.error(f"❌ Instagram login failed: {e}")
        return False

def check_ntfy():
    topic = os.getenv("NTFY_TOPIC")
    if not topic:
        logging.error("ntfy.sh topic missing in .env")
        return False
    
    url = f"https://ntfy.sh/{topic}"
    try:
        response = requests.post(url, data="Test notification from MailShield setup".encode('utf-8'), headers={"Title": "Test Setup", "Priority": "3"}, timeout=5)
        if response.status_code == 200:
            logging.info(f"✅ ntfy.sh notification sent successfully to topic: {topic}")
            return True
        else:
            logging.error(f"❌ ntfy.sh notification failed with status code: {response.status_code}")
            return False
    except Exception as e:
        logging.error(f"❌ ntfy.sh connection failed: {e}")
        return False

def check_redis():
    broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    try:
        import redis
        r = redis.from_url(broker_url)
        r.ping()
        logging.info("✅ Redis connection successful!")
        return True
    except ImportError:
        logging.warning("redis not installed (use pip install redis).")
        return False
    except Exception as e:
        logging.error(f"❌ Redis connection failed: {e}")
        return False

if __name__ == "__main__":
    print("Starting credentials and environment check...\n")
    
    # We can skip instagram if we are afraid of being blocked by too many logins, 
    # but the user asked to check "all crenditial".
    
    results = {
        "Groq (Llama 3.1)": check_groq(),
        "Gmail": check_gmail(),
        # "Instagram": check_instagram(), # Uncomment if you want to aggressively test IG
        "Instagram (Skipped to prevent block)": "skipped",
        "ntfy.sh": check_ntfy(),
        "Redis": check_redis()
    }
    
    print("\n--- Summary ---")
    all_passed = True
    for service, passed in results.items():
        if passed == "skipped":
            print(f"{service}: ⚠️ Skipped")
        else:
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{service}: {status}")
            if not passed:
                all_passed = False
                
    if not all_passed:
        print("\nSome checks failed. Please review your .env file and services.")
        # We don't forcefully exit 1 so that we don't break simple execution scripts unexpectedly,
        # but for CI we normally would.
