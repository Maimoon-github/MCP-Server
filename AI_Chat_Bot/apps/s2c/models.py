"""
S2C (Server-to-Client) Elicitation persistence models.

Any server instance can audit elicitation records via shared DB.
The resume state itself travels in the signed requestState token (true stateless).
"""
import uuid
from django.db import models
from django.utils import timezone


class ElicitationRecord(models.Model):
    """
    Audit trail for server-to-client elicitation events.
    Not required for resumption (state is in the token), but essential
    for horizontal scaling observability and debugging.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('answered', 'Answered'),
        ('completed', 'Completed'),
        ('expired', 'Expired'),
    ]

    record_id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    state_token_hash = models.CharField(
        max_length=64, db_index=True, unique=True,
        help_text="SHA-256 hash of the encoded requestState token"
    )
    operation_type = models.CharField(
        max_length=100, db_index=True,
        help_text="Category of operation being elicited (e.g., web_search, confirmation)"
    )
    original_method = models.CharField(
        max_length=100,
        help_text="JSON-RPC method that triggered the elicitation"
    )
    original_params = models.JSONField(
        help_text="Snapshot of original request params at elicitation time"
    )
    question = models.TextField(
        help_text="The prompt displayed to the user"
    )
    answer_payload = models.JSONField(
        null=True, blank=True,
        help_text="User's answer received in retry request"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(
        help_text="Token expiry; record can be cleaned up after this"
    )

    class Meta:
        db_table = 's2c_elicitation_records'
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['operation_type', 'status']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.operation_type}:{self.status} [{self.record_id}]"

    def is_expired(self):
        return timezone.now() > self.expires_at

    def mark_answered(self, answer: dict):
        self.status = 'answered'
        self.answer_payload = answer
        self.answered_at = timezone.now()
        self.save(update_fields=['status', 'answer_payload', 'answered_at'])

    def mark_completed(self):
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at'])

    def mark_expired(self):
        self.status = 'expired'
        self.save(update_fields=['status'])
