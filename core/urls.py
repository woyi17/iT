from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('', views.login_view, name='home'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),

    # Employee
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('attendance/checkin/', views.checkin_view, name='checkin'),
    path('history/', views.history_view, name='history'),
    path('correction/request/<int:record_id>/', views.correction_request_view, name='correction_request'),

    # Admin
    path('admin/dashboard/', views.admin_dashboard_view, name='admin_dashboard'),
    path('admin/attendance/api/', views.admin_attendance_api, name='admin_attendance_api'),
    path('admin/corrections/', views.admin_corrections_view, name='admin_corrections'),
    path('admin/corrections/<int:correction_id>/review/', views.admin_review_correction, name='admin_review_correction'),
    path('admin/export/', views.export_csv_view, name='export_csv'),
]
