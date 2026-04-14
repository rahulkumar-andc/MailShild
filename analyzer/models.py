from django.db import models

class Message(models.Model):
    SOURCE_CHOICES = [
        ('gmail', 'Gmail'),
        ('instagram', 'Instagram'),
    ]

    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    message_id = models.CharField(max_length=255, unique=True)
    sender = models.CharField(max_length=255)
    subject = models.CharField(max_length=500, blank=True, null=True)
    body = models.TextField()
    
    category = models.CharField(max_length=50, blank=True, null=True)
    spam_score = models.IntegerField(default=0)
    priority = models.CharField(max_length=20, blank=True, null=True)
    reason = models.TextField(blank=True, null=True)
    is_phishing = models.BooleanField(default=False)
    
    should_notify = models.BooleanField(default=False)
    notified = models.BooleanField(default=False)
    
    received_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=['-received_at']),
            models.Index(fields=['source']),
            models.Index(fields=['category']),
        ]

    def __str__(self):
        return f"[{self.source.upper()}] {self.sender} - {self.category}"
