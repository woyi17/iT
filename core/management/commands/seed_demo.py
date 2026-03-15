"""
Management command: seed demo data for development.
Usage: python manage.py seed_demo
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import date, timedelta
import random

from core.models import Department, UserProfile, AttendanceRecord, CorrectionRequest


class Command(BaseCommand):
    help = 'Seeds demo data: departments, employees, admin, and attendance records'

    def handle(self, *args, **options):
        self.stdout.write('Seeding demo data...')

        # Departments
        dept_names = ['Engineering', 'HR', 'Marketing', 'Finance']
        depts = {}
        for name in dept_names:
            dept, _ = Department.objects.get_or_create(dept_name=name)
            depts[name] = dept

        # Admin user
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={'email': 'admin@example.com', 'first_name': 'Admin', 'last_name': 'User'}
        )
        if created:
            admin_user.set_password('admin123')
            admin_user.save()
        UserProfile.objects.get_or_create(
            user=admin_user,
            defaults={'role': 'admin', 'department': depts['HR']}
        )

        # Employee users
        employees = [
            ('eren', 'Eren', 'Yeager', 'Engineering'),
            ('levi', 'Levi', 'Ackerman', 'Engineering'),
            ('erwin', 'Erwin', 'Smith', 'Marketing'),
            ('mikasa', 'Mikasa', 'Ackerman', 'Finance'),
            ('armin', 'Armin', 'Arlert', 'HR'),
        ]

        emp_users = []
        for username, first, last, dept_name in employees:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={'first_name': first, 'last_name': last, 'email': f'{username}@example.com'}
            )
            if created:
                user.set_password('pass123')
                user.save()
            UserProfile.objects.get_or_create(
                user=user,
                defaults={'role': 'employee', 'department': depts[dept_name]}
            )
            emp_users.append(user)

        # Attendance records for last 7 days
        today = date.today()
        statuses = ['on_time', 'late', 'missing']
        weights = [0.6, 0.25, 0.15]
        notes = [
            'WFH today', 'In office', 'Client meeting in the morning',
            'Doctor appointment', '', '', ''
        ]

        for user in emp_users:
            for days_ago in range(7):
                work_date = today - timedelta(days=days_ago)
                # Skip weekends
                if work_date.weekday() >= 5:
                    continue
                status = random.choices(statuses, weights=weights)[0]
                if not AttendanceRecord.objects.filter(user=user, work_date=work_date).exists():
                    check_in = None
                    check_out = None
                    if status != 'missing':
                        hour = 8 if status == 'on_time' else random.randint(9, 11)
                        check_in = timezone.make_aware(
                            timezone.datetime(work_date.year, work_date.month, work_date.day, hour, random.randint(0, 59))
                        )
                        check_out = check_in + timedelta(hours=8, minutes=random.randint(0, 30))
                    AttendanceRecord.objects.create(
                        user=user,
                        work_date=work_date,
                        check_in_time=check_in,
                        check_out_time=check_out,
                        status=status,
                        note=random.choice(notes),
                    )

        # Add one pending correction request
        first_emp = emp_users[0]
        old_record = AttendanceRecord.objects.filter(user=first_emp).last()
        if old_record and not hasattr(old_record, 'correction_request'):
            try:
                CorrectionRequest.objects.create(
                    record=old_record,
                    reason='I actually checked in on time but the system recorded me as late.',
                )
            except Exception:
                pass

        self.stdout.write(self.style.SUCCESS('[OK] Demo data seeded successfully!'))
        self.stdout.write('  Admin login: admin / admin123')
        self.stdout.write('  Employee logins: eren, levi, erwin, mikasa, armin / pass123')
