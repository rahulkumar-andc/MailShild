import logging
import imaplib
import email
from email.header import decode_header
from django.conf import settings
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)


def fetch_unseen_emails():
    """
    Connects to Gmail via IMAP, fetches UNSEEN emails, and returns them as a list of dicts.
    """
    if not settings.GMAIL_USER or not settings.GMAIL_APP_PASSWORD:
        logger.warning("Gmail credentials not configured. Skipping.")
        return []

    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        mail.login(settings.GMAIL_USER, settings.GMAIL_APP_PASSWORD)
    except Exception as e:
        logger.error("Failed to login to Gmail: %s", e)
        return []

    mail.select("inbox")

    # Fetch all unseen emails
    status, messages = mail.search(None, "UNSEEN")
    if status != "OK" or not messages[0]:
        mail.logout()
        return []

    email_ids = messages[0].split()
    fetched_emails = []

    for email_id in email_ids:
        res, msg_data = mail.fetch(email_id, "(RFC822)")
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])

                # Decode subject
                subject, encoding = decode_header(msg.get("Subject", ""))[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding if encoding else "utf-8", errors="ignore")

                sender = msg.get("From", "")
                message_id = msg.get("Message-ID", "").strip("<>")
                if not message_id:
                    message_id = f"gmail_{email_id.decode('utf-8')}"

                date_str = msg.get("Date")
                received_at = parsedate_to_datetime(date_str) if date_str else None

                # Fetch body
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        content_disposition = str(part.get("Content-Disposition"))

                        try:
                            if content_type == "text/plain" and "attachment" not in content_disposition:
                                body = part.get_payload(decode=True).decode(errors="ignore")
                                break
                        except Exception:
                            pass
                else:
                    body = msg.get_payload(decode=True).decode(errors="ignore")

                fetched_emails.append({
                    "source": "gmail",
                    "message_id": message_id,
                    "sender": sender,
                    "subject": subject,
                    "body": body,
                    "received_at": received_at,
                })

        # Mark email as SEEN
        mail.store(email_id, '+FLAGS', '\\Seen')

    mail.logout()
    logger.info("Fetched %d unseen emails from Gmail.", len(fetched_emails))
    return fetched_emails
