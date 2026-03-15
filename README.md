# Employee Sign-in Management System

**Team:** Gexiang Wu, Junyi Shen, Qikang Huang  
**University of Glasgow — Internet Technology Group Project**

---

## Tech Stack
- **Backend:** Django (Python)
- **Database:** SQLite (development) / PostgreSQL (production)
- **Frontend:** Django Templates + Vanilla JS (AJAX for check-in/out and admin filters)
- **Auth:** Django session-based auth + RBAC (employee / admin)

---

## Quick Setup

### 1. Install dependencies
```bash
pip install django
```

### 2. Run migrations
```bash
cd attendance_system
python manage.py makemigrations core
python manage.py migrate
```

### 3. Seed demo data (optional)
```bash
python manage.py seed_demo
```
This creates:
- **Admin:** `admin` / `admin123`
- **Employees:** `eren`, `levi`, `erwin`, `mikasa`, `armin` / `pass123`
- 7 days of realistic attendance records

### 4. Run the development server
```bash
python manage.py runserver
```

Open http://127.0.0.1:8000/

---

## User Stories Implemented

| Story | Description | Status |
|-------|-------------|--------|
| M1 | Authentication (register/login/logout) + RBAC | ✅ Done |
| M2 | Check-in with optional note (AJAX, no page reload) | ✅ Done |
| M3 | Check-out + duration calculation | ✅ Done |
| M4 | View my attendance history | ✅ Done |
| M5 | Admin team attendance view (date + department filter, AJAX) | ✅ Done |
| S2 | Employee submits correction request with reason | ✅ Done |
| S3 | Admin approves/rejects correction requests | ✅ Done |
| C1 | Export attendance data as CSV | ✅ Done |

---

## Pages / Routes

| URL | Page | Access |
|-----|------|--------|
| `/login/` | Login Page | Public |
| `/register/` | Register | Public |
| `/dashboard/` | Check-in Page | Employee |
| `/history/` | My History | Employee |
| `/correction/request/<id>/` | Correction Form | Employee |
| `/admin/dashboard/` | Admin Dashboard | Admin |
| `/admin/corrections/` | Correction Review | Admin |
| `/admin/export/` | Export CSV | Admin |

---

## Key Business Rules

1. **One record per user per day** — enforced via `UNIQUE(user, work_date)` constraint
2. **Status derived from check-in time:**
   - Before 09:00 → `on_time`
   - After 09:00 → `late`
   - No check-in → `missing`
3. **Correction requests:** `reviewed_by` is NULL while `status = pending`; set on approve/reject

---

## AJAX Interactions

**Check-in / Check-out (dashboard.html)**  
`POST /attendance/checkin/` — returns JSON, updates UI without page reload:
- Toggles button between Check-In ↔ Check-Out
- Updates "Has Checked In Today: Yes/No" indicator
- Shows status feedback message

**Admin Dashboard Filters (admin_dashboard.html)**  
`GET /admin/attendance/api/?date=&department=` — returns JSON array of records:
- Date + department dropdowns trigger async table reload
- Stats counters (on-time / late / missing / total) update dynamically

---

## Running Tests

```bash
python manage.py test core
```

Tests cover:
- Model constraints (unique per day, correction uniqueness, reviewed_by rule)
- Check-in/out logic (note saved, duration calculated, status computed)
- Permission checks (unauthenticated redirect, employee→admin access denied)
- Admin correction approve/reject flow
- AuditLog creation on login and check-in

---

## Accessibility (WCAG)

- Strong colour contrast for status labels (text + colour, not colour alone)
- Full keyboard navigation (tab, enter, space)
- ARIA labels on all interactive elements
- `aria-live` regions for dynamic content (AJAX feedback, clock)
- Meaningful page `<title>` tags
- Error messages via Django `messages` framework

---

## Project Structure

```
attendance_system/
├── attendance_system/        # Django project config
│   ├── settings.py
│   └── urls.py
├── core/                     # Main app
│   ├── models.py             # Department, UserProfile, AttendanceRecord, CorrectionRequest, AuditLog
│   ├── views.py              # All views (auth, employee, admin)
│   ├── urls.py               # URL routing
│   ├── tests.py              # Unit + integration tests
│   ├── management/
│   │   └── commands/
│   │       └── seed_demo.py  # Demo data seeder
│   ├── templates/core/
│   │   ├── base.html
│   │   ├── login.html
│   │   ├── register.html
│   │   ├── dashboard.html        # Check-in page
│   │   ├── history.html
│   │   ├── correction_form.html
│   │   ├── admin_dashboard.html
│   │   └── admin_corrections.html
│   └── static/core/
│       ├── css/main.css
│       └── js/app.js
└── manage.py
```
