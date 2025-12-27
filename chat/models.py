from django.db import models
from django.utils import timezone
import uuid

class ChatSession(models.Model):
    MODE_CHOICES = [
        ('genz', 'GenZ Mode'),
        ('parent', 'Parent Mode'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default='genz')
    title = models.CharField(max_length=200, default='New Conversation')
    session_key = models.CharField(max_length=100, db_index=True)  # Browser session identifier
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    message_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_comparison = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['session_key', 'mode', '-updated_at']),
        ]
    
    def __str__(self):
        return f"{self.title} ({self.get_mode_display()})"
    
    def update_title_from_message(self, message):
        """Generate a title with date/time and first question"""
        if self.title == 'New Conversation' and message:
            # Create a title with current date and time
            now = timezone.now()
            title = now.strftime("%b %d, %Y %I:%M %p")  # Format: "Dec 25, 2024 02:30 PM"
            self.title = title
            self.save()
    
    def get_first_question_preview(self):
        """Get the first user message as preview"""
        first_user_message = self.messages.filter(role='user').first()
        if first_user_message:
            content = first_user_message.content[:80]
            if len(first_user_message.content) > 80:
                content += '...'
            return content
        return "No messages yet"

class ChatMessage(models.Model):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ]
    
    MESSAGE_TYPE_CHOICES = [
        ('normal', 'Normal'),
        ('bridge', 'Bridge'),      # Bridge response (with prompts)
        ('baseline', 'Baseline'),  # Baseline response (without prompts)
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPE_CHOICES, default='normal')
    content = models.TextField()
    thinking = models.TextField(null=True, blank=True)
    tokens = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    user_message = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, 
                                     related_name='assistant_responses')
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.role}: {self.content[:50]}"
    
    def save(self, *args, **kwargs):
        # Update session's message count and timestamp
        super().save(*args, **kwargs)
        self.session.message_count = ChatMessage.objects.filter(session=self.session).count()
        self.session.save()