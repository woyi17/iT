from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Department(models.Model):
    dept_name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.dept_name


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('employee', 'Employee'),
        ('admin', 'Admin / Manager'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='employee')
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='members'
    )

    def __str__(self):
        return f"{self.user.username} ({self.role})"

    @property
    def is_admin(self):
        return self.role == 'admin'


class AttendanceRecord(models.Model):
    STATUS_CHOICES = [
        ('on_time', 'On Time'),
        ('late', 'Late'),
        ('missing', 'Missing'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attendance_records')
    work_date = models.DateField()
    check_in_time = models.DateTimeField(null=True, blank=True)
    check_out_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='missing')
    note = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'work_date')
        ordering = ['-work_date']

    def __str__(self):
        return f"{self.user.username} - {self.work_date} - {self.status}"

    @property
    def duration(self):
        """Returns working duration as a formatted string."""
        if self.check_in_time and self.check_out_time:
            delta = self.check_out_time - self.check_in_time
            total_seconds = int(delta.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            return f"{hours}h {minutes}m"
        return None

    def compute_status(self):
        """Derive status from check_in_time against the cutoff rule."""
        from django.conf import settings
        cutoff_hour = getattr(settings, 'CHECKIN_CUTOFF_HOUR', 9)
        cutoff_minute = getattr(settings, 'CHECKIN_CUTOFF_MINUTE', 0)
        if not self.check_in_time:
            return 'missing'
        local_time = timezone.localtime(self.check_in_time)
        cutoff = local_time.replace(hour=cutoff_hour, minute=cutoff_minute, second=0, microsecond=0)
        if local_time <= cutoff:
            return 'on_time'
        return 'late'


class CorrectionRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    record = models.OneToOneField(
        AttendanceRecord, on_delete=models.CASCADE, related_name='correction_request'
    )
    request_type = models.CharField(max_length=100, default='attendance_correction')
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_corrections'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Correction for {self.record} [{self.status}]"

    def save(self, *args, **kwargs):
        # Enforce: reviewed_by must be null when pending
        if self.status == 'pending':
            self.reviewed_by = None
        super().save(*args, **kwargs)


class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='audit_logs')
    action = models.CharField(max_length=100)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user.username} - {self.action} at {self.timestamp}"
