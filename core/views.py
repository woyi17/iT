import json
import csv
from datetime import date, timedelta

from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.db import IntegrityError
from django.contrib import messages

from .models import UserProfile, Department, AttendanceRecord, CorrectionRequest, AuditLog


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def log_action(user, action, details=''):
    AuditLog.objects.create(user=user, action=action, details=details)


def admin_required(view_func):
    """Decorator: user must be logged in AND have admin role."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        try:
            if not request.user.profile.is_admin:
                messages.error(request, 'Access denied: Admin privileges required.')
                return redirect('dashboard')
        except UserProfile.DoesNotExist:
            messages.error(request, 'Access denied.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


def get_or_create_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


# ─────────────────────────────────────────────
# Auth Views
# ─────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            log_action(user, 'login')
            profile = get_or_create_profile(user)
            if profile.is_admin:
                return redirect('admin_dashboard')
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')

    return render(request, 'core/login.html')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    departments = Department.objects.all()

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')
        dept_id = request.POST.get('department', '')
        role = request.POST.get('role', 'employee')

        if not username or not password:
            messages.error(request, 'Username and password are required.')
        elif password != password2:
            messages.error(request, 'Passwords do not match.')
        elif User.objects.filter(username=username).exists():
            messages.error(request, 'Username already taken.')
        else:
            user = User.objects.create_user(username=username, email=email, password=password)
            profile = UserProfile(user=user, role=role)
            if dept_id:
                try:
                    profile.department = Department.objects.get(pk=dept_id)
                except Department.DoesNotExist:
                    pass
            profile.save()
            login(request, user)
            log_action(user, 'register')
            messages.success(request, f'Welcome, {username}! Your account has been created.')
            if profile.is_admin:
                return redirect('admin_dashboard')
            return redirect('dashboard')

    return render(request, 'core/register.html', {'departments': departments})


def logout_view(request):
    if request.user.is_authenticated:
        log_action(request.user, 'logout')
    logout(request)
    return redirect('login')


# ─────────────────────────────────────────────
# Employee Views
# ─────────────────────────────────────────────

@login_required
def dashboard_view(request):
    """Check-in Page: show today's status and check-in/out buttons."""
    today = date.today()
    record = AttendanceRecord.objects.filter(user=request.user, work_date=today).first()
    profile = get_or_create_profile(request.user)
    return render(request, 'core/dashboard.html', {
        'today': today,
        'record': record,
        'profile': profile,
    })


@login_required
@require_POST
def checkin_view(request):
    """AJAX endpoint: handle check-in or check-out."""
    today = date.today()
    now = timezone.now()
    record, created = AttendanceRecord.objects.get_or_create(
        user=request.user,
        work_date=today,
        defaults={'check_in_time': now, 'note': ''}
    )

    data = json.loads(request.body) if request.content_type == 'application/json' else {}
    note = data.get('note', request.POST.get('note', ''))

    if created:
        # First action of the day → check-in
        record.note = note
        record.status = record.compute_status()
        record.save()
        log_action(request.user, 'check_in', f'status={record.status}')
        return JsonResponse({
            'ok': True,
            'action': 'check_in',
            'status': record.status,
            'check_in_time': timezone.localtime(record.check_in_time).strftime('%H:%M:%S'),
            'message': f'Checked in successfully — status: {record.get_status_display()}',
        })
    elif record.check_in_time and not record.check_out_time:
        # Already checked in → check-out
        record.check_out_time = now
        record.save()
        log_action(request.user, 'check_out', f'duration={record.duration}')
        return JsonResponse({
            'ok': True,
            'action': 'check_out',
            'status': record.status,
            'check_out_time': timezone.localtime(record.check_out_time).strftime('%H:%M:%S'),
            'duration': record.duration,
            'message': f'Checked out successfully — duration: {record.duration}',
        })
    else:
        return JsonResponse({'ok': False, 'message': 'Already checked out for today.'})


@login_required
def history_view(request):
    """M4: My attendance history."""
    records = AttendanceRecord.objects.filter(user=request.user).order_by('-work_date')
    profile = get_or_create_profile(request.user)
    return render(request, 'core/history.html', {
        'records': records,
        'profile': profile,
    })


@login_required
def correction_request_view(request, record_id):
    """S2: Submit a correction request for a specific attendance record."""
    record = get_object_or_404(AttendanceRecord, pk=record_id, user=request.user)

    # Check if a request already exists
    existing = CorrectionRequest.objects.filter(record=record).first()

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, 'Please provide a reason for the correction request.')
        elif existing:
            messages.warning(request, 'A correction request already exists for this record.')
            return redirect('history')
        else:
            CorrectionRequest.objects.create(record=record, reason=reason)
            log_action(request.user, 'correction_request', f'record_id={record.id}')
            messages.success(request, 'Correction request submitted successfully.')
            return redirect('history')

    profile = get_or_create_profile(request.user)
    return render(request, 'core/correction_form.html', {
        'record': record,
        'existing': existing,
        'profile': profile,
    })


# ─────────────────────────────────────────────
# Admin Views
# ─────────────────────────────────────────────

@admin_required
def admin_dashboard_view(request):
    """M5: Admin sees all team attendance with date + department filter."""
    departments = Department.objects.all()
    filter_date = request.GET.get('date', str(date.today()))
    filter_dept = request.GET.get('department', '')

    # If AJAX request, return JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return _admin_attendance_json(filter_date, filter_dept)

    records = _get_filtered_records(filter_date, filter_dept)
    profile = get_or_create_profile(request.user)
    return render(request, 'core/admin_dashboard.html', {
        'departments': departments,
        'filter_date': filter_date,
        'filter_dept': filter_dept,
        'records': records,
        'profile': profile,
    })


@admin_required
def admin_attendance_api(request):
    """AJAX endpoint: returns filtered attendance records as JSON."""
    filter_date = request.GET.get('date', str(date.today()))
    filter_dept = request.GET.get('department', '')
    records = _get_filtered_records(filter_date, filter_dept)
    data = []
    for r in records:
        data.append({
            'id': r.id,
            'employee': r.user.get_full_name() or r.user.username,
            'department': r.user.profile.department.dept_name if hasattr(r.user, 'profile') and r.user.profile.department else '—',
            'work_date': str(r.work_date),
            'check_in_time': timezone.localtime(r.check_in_time).strftime('%H:%M') if r.check_in_time else '—',
            'check_out_time': timezone.localtime(r.check_out_time).strftime('%H:%M') if r.check_out_time else '—',
            'duration': r.duration or '—',
            'status': r.status,
            'status_display': r.get_status_display(),
            'note': r.note or '',
        })
    return JsonResponse({'records': data})


def _get_filtered_records(filter_date, filter_dept):
    qs = AttendanceRecord.objects.select_related('user', 'user__profile', 'user__profile__department')
    if filter_date:
        try:
            qs = qs.filter(work_date=filter_date)
        except Exception:
            pass
    if filter_dept:
        qs = qs.filter(user__profile__department__id=filter_dept)
    return qs.order_by('user__username')


@admin_required
def admin_corrections_view(request):
    """S3: Admin reviews correction requests."""
    status_filter = request.GET.get('status', 'pending')
    corrections = CorrectionRequest.objects.select_related(
        'record', 'record__user', 'reviewed_by'
    ).filter(status=status_filter).order_by('-created_at')
    profile = get_or_create_profile(request.user)
    return render(request, 'core/admin_corrections.html', {
        'corrections': corrections,
        'status_filter': status_filter,
        'profile': profile,
    })


@admin_required
@require_POST
def admin_review_correction(request, correction_id):
    """S3: Approve or reject a correction request."""
    correction = get_object_or_404(CorrectionRequest, pk=correction_id)
    action = request.POST.get('action')
    if action in ('approved', 'rejected'):
        correction.status = action
        correction.reviewed_by = request.user
        correction.save()
        log_action(request.user, f'correction_{action}', f'correction_id={correction.id}')
        messages.success(request, f'Correction request {action}.')
    return redirect('admin_corrections')


@admin_required
def export_csv_view(request):
    """C1: Export attendance data as CSV."""
    filter_date = request.GET.get('date', '')
    filter_dept = request.GET.get('department', '')
    records = _get_filtered_records(filter_date, filter_dept)

    response = HttpResponse(content_type='text/csv')
    filename = f'attendance_{filter_date or "all"}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(['Employee', 'Department', 'Date', 'Check-In', 'Check-Out', 'Duration', 'Status', 'Note'])
    for r in records:
        dept = r.user.profile.department.dept_name if hasattr(r.user, 'profile') and r.user.profile.department else ''
        writer.writerow([
            r.user.get_full_name() or r.user.username,
            dept,
            r.work_date,
            timezone.localtime(r.check_in_time).strftime('%H:%M') if r.check_in_time else '',
            timezone.localtime(r.check_out_time).strftime('%H:%M') if r.check_out_time else '',
            r.duration or '',
            r.get_status_display(),
            r.note,
        ])
    return response
