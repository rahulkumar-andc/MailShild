import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from analyzer.insta_fetcher import _get_client, SESSION_FILE
import json

cl = _get_client()
cl.load_settings(SESSION_FILE)

result = cl.private_request("direct_v2/inbox/", params={
    "visual_message_return_type": "unseen",
    "thread_message_limit": "5",
    "persistentBadging": "true",
    "limit": "2",
})

threads = result.get("inbox", {}).get("threads", [])
print(json.dumps(threads[:1], indent=2))
