from django.db import models

class Message(models.Model):
    SOURCE_CHOICES = [
        ('gmail', 'Gmail'),
        ('instagram', 'Instagram'),
        ('whatsapp', 'WhatsApp'),
    ]

    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    message_id = models.CharField(max_length=255, unique=True)
    sender = models.CharField(max_length=255)
    sender_external_id = models.CharField(max_length=255, blank=True, null=True, help_text="Platform-specific ID (IG PK or WA JID)")

    subject = models.CharField(max_length=500, blank=True, null=True)
    body = models.TextField()
    
    category = models.CharField(max_length=50, blank=True, null=True)
    spam_score = models.IntegerField(default=0)
    priority = models.CharField(max_length=20, blank=True, null=True)
    reason = models.TextField(blank=True, null=True)
    is_phishing = models.BooleanField(default=False)
    
    should_notify = models.BooleanField(default=False)
    notified = models.BooleanField(default=False)
    urls_scanned = models.BooleanField(default=False)
    ai_reply_draft = models.TextField(blank=True, null=True, help_text="AI-pre-generated draft for this message")
    auto_replied = models.BooleanField(default=False, help_text="Whether an automated reply was sent for this message")
    
    received_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=['-received_at']),
            models.Index(fields=['source']),
            models.Index(fields=['category']),
        ]

    def __str__(self):
        return f"[{self.source.upper()}] {self.sender} - {self.category}"

class FavouriteUser(models.Model):
    username = models.CharField(max_length=255, unique=True)
    source = models.CharField(max_length=20, choices=Message.SOURCE_CHOICES, default='instagram')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.username} ({self.source})"


class MonitoredWhatsAppGroup(models.Model):
    group_id = models.CharField(max_length=100, unique=True, help_text="WhatsApp group JID e.g. 120363xxx@g.us")
    group_name = models.CharField(max_length=255)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.group_name} ({'active' if self.active else 'paused'})"

class Reminder(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='reminders', null=True, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    source = models.CharField(max_length=20, choices=Message.SOURCE_CHOICES, default='whatsapp')
    remind_at = models.DateTimeField()
    is_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['remind_at', 'is_sent']),
        ]

    def __str__(self):
        status = "✅ Sent" if self.is_sent else "⏰ Pending"
        return f"[{status}] {self.title} — {self.remind_at}"


class URLScan(models.Model):
    """Stores URL safety scan results linked to a message."""
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='url_scans')
    url = models.URLField(max_length=2048)
    is_safe = models.BooleanField(default=True)
    risk_score = models.IntegerField(default=0)
    flags = models.JSONField(default=list, blank=True)
    scanned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['is_safe']),
        ]

    def __str__(self):
        status = "✅ Safe" if self.is_safe else f"🔴 Risk {self.risk_score}"
        return f"[{status}] {self.url[:60]}"

