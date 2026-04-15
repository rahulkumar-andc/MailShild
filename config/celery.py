import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('config')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'scan-gmail-every-5-mins': {
        'task': 'analyzer.tasks.scan_gmail',
        'schedule': 300.0,
    },
    'scan-instagram-every-5-mins': {
        'task': 'analyzer.tasks.scan_instagram',
        'schedule': 300.0,
    },
    'check-reminders-every-60s': {
        'task': 'analyzer.tasks.check_reminders',
        'schedule': 60.0,
    },
    'clean-old-spam-daily': {
        'task': 'analyzer.tasks.clean_old_spam',
        'schedule': crontab(hour=0, minute=0),
    },
    'send-daily-briefing': {
        'task': 'analyzer.tasks.send_daily_briefing',
        'schedule': crontab(hour=8, minute=0),
    },
    # 🎂 Birthday Auto-Reply — scans every 2 min for wishes
    'auto-reply-birthday-wishes': {
        'task': 'analyzer.tasks.auto_reply_birthday_wishes',
        'schedule': 120.0,
    },
}

