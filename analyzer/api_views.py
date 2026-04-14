import json
import logging
from datetime import datetime, timezone

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings

from .models import Message
from .tasks import process_message_task

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def receive_wa_message(request):
    """
    API endpoint for WhatsApp bridge.
    Receives group messages from the Node.js bridge and queues them for processing.
    Protected by a shared secret token.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    # Validate shared secret
    secret = data.get("secret", "")
    expected_secret = getattr(settings, 'WA_BRIDGE_SECRET', 'mailshield-wa-secret-2026')
    if secret != expected_secret:
        logger.warning("WhatsApp bridge: invalid secret received")
        return JsonResponse({"error": "Unauthorized"}, status=403)

    # Extract fields
    group_id = data.get("group_id", "")
    group_name = data.get("group_name", "Unknown Group")
    sender = data.get("sender", "Unknown")
    body = data.get("body", "")
    message_id = data.get("message_id", "")
    timestamp = data.get("timestamp")

    if not body or not message_id:
        return JsonResponse({"error": "Missing body or message_id"}, status=400)

    # Build unique message ID
    wa_msg_id = f"wa_{message_id}"

    # Skip if already processed
    if Message.objects.filter(message_id=wa_msg_id).exists():
        return JsonResponse({"status": "duplicate", "message": "Already processed"})

    # Parse timestamp
    received_at = None
    if timestamp:
        try:
            received_at = datetime.fromtimestamp(int(timestamp), tz=timezone.utc).isoformat()
        except (ValueError, TypeError):
            received_at = None

    # Build message data for Celery task
    msg_data = {
        "source": "whatsapp",
        "message_id": wa_msg_id,
        "sender": sender,
        "subject": f"WhatsApp: {group_name}",
        "body": body,
        "received_at": received_at,
        "group_id": group_id,
        "group_name": group_name,
    }

    # Dispatch to Celery
    process_message_task.delay(msg_data)

    logger.info("WhatsApp message queued: [%s] %s: %s...", group_name, sender, body[:50])
    return JsonResponse({"status": "queued", "message_id": wa_msg_id})
