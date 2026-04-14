from django.contrib import admin
from .models import Message

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('source', 'sender', 'category', 'is_phishing', 'spam_score', 'should_notify', 'notified', 'received_at')
    list_filter = ('source', 'category', 'is_phishing', 'should_notify', 'notified')
    search_fields = ('sender', 'subject', 'body', 'reason')
    ordering = ('-received_at',)
