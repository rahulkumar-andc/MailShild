import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from analyzer.models import Message

def check_gaurav():
    print("Searching for 'Gaurav'...")
    msgs = Message.objects.filter(sender__icontains='Gaurav')
    print(f"Found {msgs.count()} messages.")
    for m in msgs[:5]:
        print(f"[{m.received_at}] {m.sender}: {m.body[:50]}...")

if __name__ == "__main__":
    check_gaurav()
