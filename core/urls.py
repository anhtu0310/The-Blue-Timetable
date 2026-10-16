from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import ThrottledLoginForm

urlpatterns = [
    path('dang-nhap/', auth_views.LoginView.as_view(
        template_name='core/login.html', authentication_form=ThrottledLoginForm,
        redirect_authenticated_user=True), name='login'),
    path('dang-xuat/', auth_views.LogoutView.as_view(), name='logout'),
    path('doi-mat-khau/', views.password_change, name='password_change'),

    path('', views.calendar, name='calendar'),
    path('api/buoi-hoc/', views.calendar_events, name='calendar_events'),
    path('thong-ke-thang/', views.month_stats, name='calendar_stats'),

    path('buoi-hoc/<int:pk>/', views.session_detail, name='session_detail'),
    path('buoi-hoc/<int:pk>/diem-danh/', views.session_attendance, name='session_attendance'),
    path('buoi-hoc/<int:pk>/dieu-chinh/', views.session_reschedule, name='session_reschedule'),
    path('buoi-hoc/<int:pk>/mo-khoa/', views.session_unlock, name='session_unlock'),

    path('lop-hoc/', views.class_list, name='class_list'),
    path('lop-hoc/them/', views.class_create, name='class_create'),
    path('lop-hoc/<int:pk>/', views.class_detail, name='class_detail'),
    path('lop-hoc/<int:pk>/sua/', views.class_edit, name='class_edit'),
    path('lop-hoc/<int:pk>/trang-thai/', views.class_status, name='class_status'),
    path('lop-hoc/<int:pk>/xoa/', views.class_delete, name='class_delete'),
    path('lop-hoc/<int:pk>/tai-lieu/', views.material_add, name='material_add'),
    path('tai-lieu/<int:pk>/xoa/', views.material_delete, name='material_delete'),

    path('ho-so/', views.me, name='me'),
    path('giao-vien/', views.teacher_list, name='teacher_list'),
    path('giao-vien/them/', views.teacher_create, name='teacher_create'),
    path('giao-vien/<int:pk>/', views.teacher_detail, name='teacher_detail'),
    path('giao-vien/<int:pk>/sua/', views.teacher_edit, name='teacher_edit'),
    path('giao-vien/<int:pk>/mat-khau/', views.teacher_password, name='teacher_password'),
    path('giao-vien/<int:pk>/xoa/', views.teacher_delete, name='teacher_delete'),

    path('hoc-sinh/', views.student_list, name='student_list'),
    path('hoc-sinh/them/', views.student_create, name='student_create'),
    path('hoc-sinh/<int:pk>/', views.student_detail, name='student_detail'),
    path('hoc-sinh/<int:pk>/sua/', views.student_edit, name='student_edit'),
    path('hoc-sinh/<int:pk>/xoa/', views.student_delete, name='student_delete'),

    path('mon-hoc/', views.subject_list, name='subject_list'),
    path('mon-hoc/<int:pk>/sua/', views.subject_edit, name='subject_edit'),
    path('mon-hoc/<int:pk>/xoa/', views.subject_delete, name='subject_delete'),
]
