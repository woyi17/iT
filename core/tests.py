"""
Unit tests for the Employee Sign-in Management System.
Run with: python manage.py test core
"""
from datetime import date, timedelta

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from django.urls import reverse

from .models import Department, UserProfile, AttendanceRecord, CorrectionRequest, AuditLog


# ─────────────────────────────────────────────
# Helper factories
# ─────────────────────────────────────────────

def make_employee(username='alice', password='testpass123'):
    user = User.objects.create_user(username=username, password=password)
    UserProfile.objects.create(user=user, role='employee')
    return user


def make_admin(username='boss', password='testpass123'):
    user = User.objects.create_user(username=username, password=password)
    UserProfile.objects.create(user=user, role='admin')
    return user


# ─────────────────────────────────────────────
# Model Tests
# ─────────────────────────────────────────────

class DepartmentModelTest(TestCase):
    def test_create_department(self):
        dept = Department.objects.create(dept_name='Engineering')
        self.assertEqual(str(dept), 'Engineering')

    def test_department_name_unique(self):
        Department.objects.create(dept_name='HR')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Department.objects.create(dept_name='HR')


class UserProfileTest(TestCase):
    def test_employee_is_not_admin(self):
        user = make_employee()
        self.assertFalse(user.profile.is_admin)

    def test_admin_is_admin(self):
        user = make_admin()
        self.assertTrue(user.profile.is_admin)

    def test_profile_str(self):
        user = make_employee('bob')
        self.assertIn('bob', str(user.profile))
        self.assertIn('employee', str(user.profile))


class AttendanceRecordModelTest(TestCase):
    def setUp(self):
        self.user = make_employee()
        self.today = date.today()

    def test_create_attendance_record(self):
        """Basic creation saves correctly."""
        now = timezone.now()
        record = AttendanceRecord.objects.create(
            user=self.user,
            work_date=self.today,
            check_in_time=now,
            note='WFH today',
        )
        record.status = record.compute_status()
        record.save()
        self.assertEqual(record.work_date, self.today)
        self.assertEqual(record.note, 'WFH today')
        self.assertIn(record.status, ['on_time', 'late'])

    def test_unique_constraint_user_per_day(self):
        """UNIQUE(user, work_date) — duplicate must raise IntegrityError."""
        AttendanceRecord.objects.create(user=self.user, work_date=self.today)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            AttendanceRecord.objects.create(user=self.user, work_date=self.today)

    def test_different_days_allowed(self):
        """Two records on different days for same user are fine."""
        yesterday = self.today - timedelta(days=1)
        r1 = AttendanceRecord.objects.create(user=self.user, work_date=self.today)
        r2 = AttendanceRecord.objects.create(user=self.user, work_date=yesterday)
        self.assertNotEqual(r1.pk, r2.pk)

    def test_duration_with_checkout(self):
        """Duration property returns HHh MMm string when both times are set."""
        now = timezone.now()
        record = AttendanceRecord.objects.create(
            user=self.user,
            work_date=self.today,
            check_in_time=now,
            check_out_time=now + timezone.timedelta(hours=8, minutes=30),
        )
        self.assertIn('8h', record.duration)
        self.assertIn('30m', record.duration)

    def test_duration_without_checkout_is_none(self):
        """Duration returns None when check_out_time is not set."""
        now = timezone.now()
        record = AttendanceRecord.objects.create(
            user=self.user, work_date=self.today, check_in_time=now
        )
        self.assertIsNone(record.duration)

    def test_status_missing_when_no_checkin(self):
        """compute_status returns 'missing' when no check_in_time."""
        record = AttendanceRecord(user=self.user, work_date=self.today)
        self.assertEqual(record.compute_status(), 'missing')

    def test_status_on_time_at_8am(self):
        """Check-in at 8:00 AM should be on_time (before 09:00 cutoff)."""
        import datetime
        dt = timezone.make_aware(
            datetime.datetime.combine(self.today, datetime.time(8, 0, 0))
        )
        record = AttendanceRecord(user=self.user, work_date=self.today, check_in_time=dt)
        self.assertEqual(record.compute_status(), 'on_time')

    def test_status_late_at_930am(self):
        """Check-in at 9:30 AM should be late (after 09:00 cutoff)."""
        import datetime
        dt = timezone.make_aware(
            datetime.datetime.combine(self.today, datetime.time(9, 30, 0))
        )
        record = AttendanceRecord(user=self.user, work_date=self.today, check_in_time=dt)
        self.assertEqual(record.compute_status(), 'late')


class CorrectionRequestModelTest(TestCase):
    def setUp(self):
        self.user = make_employee()
        self.record = AttendanceRecord.objects.create(
            user=self.user, work_date=date.today()
        )

    def test_create_correction_pending(self):
        """New correction request is pending and reviewed_by is null."""
        cr = CorrectionRequest.objects.create(record=self.record, reason='Missed check-out')
        self.assertEqual(cr.status, 'pending')
        self.assertIsNone(cr.reviewed_by)

    def test_one_correction_per_record(self):
        """Each AttendanceRecord can have at most one CorrectionRequest."""
        CorrectionRequest.objects.create(record=self.record, reason='First request')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            CorrectionRequest.objects.create(record=self.record, reason='Second request')

    def test_reviewed_by_cleared_when_set_to_pending(self):
        """If status is reset to pending, reviewed_by becomes null on save."""
        admin = make_admin()
        cr = CorrectionRequest.objects.create(
            record=self.record, reason='test', status='approved', reviewed_by=admin
        )
        cr.status = 'pending'
        cr.save()
        cr.refresh_from_db()
        self.assertIsNone(cr.reviewed_by)


# ─────────────────────────────────────────────
# View / Integration Tests
# ─────────────────────────────────────────────

class AuthViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_employee()

    def test_login_page_renders(self):
        resp = self.client.get(reverse('login'))
        self.assertEqual(resp.status_code, 200)

    def test_login_with_valid_credentials(self):
        resp = self.client.post(reverse('login'), {
            'username': 'alice', 'password': 'testpass123'
        })
        self.assertEqual(resp.status_code, 302)  # redirect after login

    def test_login_with_invalid_credentials(self):
        resp = self.client.post(reverse('login'), {
            'username': 'alice', 'password': 'wrongpassword'
        })
        self.assertEqual(resp.status_code, 200)  # stays on login page
        self.assertContains(resp, 'Invalid')

    def test_register_creates_user_and_profile(self):
        resp = self.client.post(reverse('register'), {
            'username': 'newuser',
            'password': 'pass12345',
            'password2': 'pass12345',
            'role': 'employee',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(User.objects.filter(username='newuser').exists())
        self.assertTrue(UserProfile.objects.filter(user__username='newuser').exists())


class AuthRedirectTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_dashboard_redirects_unauthenticated(self):
        """Unauthenticated users accessing /dashboard/ are redirected to login."""
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp['Location'])

    def test_history_redirects_unauthenticated(self):
        resp = self.client.get(reverse('history'))
        self.assertEqual(resp.status_code, 302)

    def test_admin_dashboard_redirects_employee(self):
        """Non-admin users cannot access the admin dashboard."""
        user = make_employee('emp2')
        self.client.login(username='emp2', password='testpass123')
        resp = self.client.get(reverse('admin_dashboard'))
        # Should redirect to employee dashboard
        self.assertEqual(resp.status_code, 302)


class CheckInViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_employee('worker')
        self.client.login(username='worker', password='testpass123')

    def test_check_in_creates_record(self):
        """POST to checkin endpoint creates an AttendanceRecord for today."""
        import json
        resp = self.client.post(
            reverse('checkin'),
            data=json.dumps({'note': 'Test note'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['action'], 'check_in')
        self.assertTrue(AttendanceRecord.objects.filter(user=self.user).exists())

    def test_note_is_saved(self):
        """Note field is persisted in the attendance record."""
        import json
        self.client.post(
            reverse('checkin'),
            data=json.dumps({'note': 'Working from Glasgow office'}),
            content_type='application/json',
        )
        record = AttendanceRecord.objects.get(user=self.user, work_date=date.today())
        self.assertEqual(record.note, 'Working from Glasgow office')

    def test_check_out_after_check_in(self):
        """Second POST triggers check-out and returns duration."""
        import json
        # First: check in
        self.client.post(
            reverse('checkin'),
            data=json.dumps({}),
            content_type='application/json',
        )
        # Second: check out
        resp = self.client.post(
            reverse('checkin'),
            data=json.dumps({}),
            content_type='application/json',
        )
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['action'], 'check_out')
        self.assertIn('duration', data)

    def test_third_post_returns_already_checked_out(self):
        """After check-out, another POST returns ok=False."""
        import json
        self.client.post(reverse('checkin'), data=json.dumps({}), content_type='application/json')
        self.client.post(reverse('checkin'), data=json.dumps({}), content_type='application/json')
        resp = self.client.post(reverse('checkin'), data=json.dumps({}), content_type='application/json')
        data = resp.json()
        self.assertFalse(data['ok'])


class AdminViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = make_admin('mgr')
        self.client.login(username='mgr', password='testpass123')

    def test_admin_dashboard_renders(self):
        resp = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(resp.status_code, 200)

    def test_admin_can_approve_correction(self):
        """Admin approving a correction sets status and reviewed_by."""
        emp = make_employee('emp3')
        record = AttendanceRecord.objects.create(user=emp, work_date=date.today())
        correction = CorrectionRequest.objects.create(record=record, reason='Test')
        resp = self.client.post(
            reverse('admin_review_correction', args=[correction.id]),
            {'action': 'approved'}
        )
        self.assertEqual(resp.status_code, 302)
        correction.refresh_from_db()
        self.assertEqual(correction.status, 'approved')
        self.assertEqual(correction.reviewed_by, self.admin)

    def test_admin_can_reject_correction(self):
        """Admin rejecting a correction sets status=rejected and reviewed_by."""
        emp = make_employee('emp4')
        record = AttendanceRecord.objects.create(user=emp, work_date=date.today())
        correction = CorrectionRequest.objects.create(record=record, reason='Test')
        self.client.post(
            reverse('admin_review_correction', args=[correction.id]),
            {'action': 'rejected'}
        )
        correction.refresh_from_db()
        self.assertEqual(correction.status, 'rejected')
        self.assertEqual(correction.reviewed_by, self.admin)

    def test_attendance_api_returns_json(self):
        resp = self.client.get(reverse('admin_attendance_api'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('records', data)

    def test_export_csv_returns_csv(self):
        resp = self.client.get(reverse('export_csv'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv')


class HistoryViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_employee('histuser')
        self.client.login(username='histuser', password='testpass123')

    def test_history_page_renders(self):
        resp = self.client.get(reverse('history'))
        self.assertEqual(resp.status_code, 200)

    def test_history_shows_user_records_only(self):
        """History page only shows records belonging to the logged-in user."""
        other = make_employee('other_emp')
        today = date.today()
        AttendanceRecord.objects.create(user=self.user, work_date=today)
        AttendanceRecord.objects.create(user=other, work_date=today - timedelta(days=1))
        resp = self.client.get(reverse('history'))
        # Only the current user's record in context
        records = list(resp.context['records'])
        self.assertTrue(all(r.user == self.user for r in records))


class AuditLogTest(TestCase):
    def test_audit_log_created_on_checkin(self):
        """Check-in action creates an AuditLog entry."""
        import json
        client = Client()
        user = make_employee('audituser')
        client.login(username='audituser', password='testpass123')
        client.post(reverse('checkin'), data=json.dumps({}), content_type='application/json')
        self.assertTrue(AuditLog.objects.filter(user=user, action='check_in').exists())

    def test_audit_log_created_on_login(self):
        """Login creates an AuditLog entry."""
        make_employee('loginuser')
        client = Client()
        client.post(reverse('login'), {'username': 'loginuser', 'password': 'testpass123'})
        user = User.objects.get(username='loginuser')
        self.assertTrue(AuditLog.objects.filter(user=user, action='login').exists())
