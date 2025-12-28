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
    session_type = models.CharField(max_length=20, default='normal', choices=[
        ('normal', 'Normal Chat'),
        ('comparison', 'Comparison Chat')
    ])
    
    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['session_key', 'mode', '-updated_at']),
        ]
    
    def __str__(self):
        return f"{self.title} ({self.get_mode_display()})"
    
    def update_title_from_message(self, message):
        """Generate a title with conversation ID"""
        if self.title.startswith("New Conversation") or self.title.startswith("Conversation -"):
            # Use first 8 characters of UUID for conversation ID
            short_id = str(self.id)[:8]
            self.title = f"Conversation {short_id}"
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
    
    @property
    def is_comparison(self):
        return self.session_type == 'comparison'

class ChatMessage(models.Model):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    thinking = models.TextField(null=True, blank=True)
    tokens = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.role}: {self.content[:50]}"
    
    def save(self, *args, **kwargs):
        # Update session's message count and timestamp
        super().save(*args, **kwargs)
        self.session.message_count = ChatMessage.objects.filter(session=self.session).count()
        self.session.save()

class ComparisonTurn(models.Model):
    """Represents one round of comparison (user message + two AI responses)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='comparison_turns')
    user_message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name='comparison_turns')
    bridge_response = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, 
                                        related_name='bridge_comparisons', null=True, blank=True)
    baseline_response = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, 
                                          related_name='baseline_comparisons', null=True, blank=True)
    turn_number = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['turn_number']
    
    def __str__(self):
        return f"Turn {self.turn_number} - {self.session.title}"
    
    @property
    def is_complete(self):
        """Check if both responses are available"""
        return self.bridge_response is not None and self.baseline_response is not None
