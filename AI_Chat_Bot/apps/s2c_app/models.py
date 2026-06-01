"""S2C App Models"""
from django.db import models

class FileRecord(models.Model):
    """Demo: Files that server can delete"""
    name = models.CharField(max_length=100)
    size_kb = models.PositiveIntegerField(default=0)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'files'

    def __str__(self):
        return self.name

class ElicitationLog(models.Model):
    """Track elicitation rounds for debugging"""
    action = models.CharField(max_length=50)
    question = models.TextField()
    answer = models.CharField(max_length=50, blank=True, null=True)
    request_state = models.TextField()
    round_number = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'elicitation_logs'
