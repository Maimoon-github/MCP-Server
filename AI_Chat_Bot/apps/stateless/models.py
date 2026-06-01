"""
Shared persistence models for MCP 2026 Stateless Server.
Any server instance can access any record — true horizontal scaling.
No conversational state storage.
"""
import uuid
from django.db import models


class Task(models.Model):
    """
    MCP Tasks Extension model.
    Distributed execution: state only in shared persistence.
    """
    TASK_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    task_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_type = models.CharField(max_length=100, default='generic', db_index=True)
    name = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=50, default='pending',
        choices=TASK_STATUS_CHOICES, db_index=True
    )

    # Payloads for distributed stateless execution
    input_payload = models.JSONField(null=True, blank=True)
    output_payload = models.JSONField(null=True, blank=True)
    error_payload = models.JSONField(null=True, blank=True)

    # Legacy result field for backward compatibility
    result = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'mcp_tasks'
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['task_type', 'status']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.task_type}:{self.name or 'untitled'} [{self.status}]"

    def mark_running(self):
        """Atomic state transition to running."""
        self.status = 'running'
        self.save(update_fields=['status', 'updated_at'])

    def mark_completed(self, output: dict = None):
        """Atomic state transition to completed."""
        from django.utils import timezone
        self.status = 'completed'
        self.output_payload = output
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'output_payload', 'completed_at', 'updated_at'])

    def mark_failed(self, error: dict = None):
        """Atomic state transition to failed."""
        from django.utils import timezone
        self.status = 'failed'
        self.error_payload = error
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'error_payload', 'completed_at', 'updated_at'])