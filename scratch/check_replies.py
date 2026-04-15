import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from analyzer.models import Message
from datetime import date

replies = Message.objects.filter(received_at__date=date.today(), auto_replied=True)
print(f"REPLIED_COUNT: {replies.count()}")
for r in replies:
    print(f" - To {r.sender} ({r.source}): {r.body[:50]}")
