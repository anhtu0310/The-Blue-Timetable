from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from simple_history.admin import SimpleHistoryAdmin

from .models import Attendance, ClassMaterial, ClassSession, Student, StudyClass, Subject, User

# The main dashboard is the normal way to manage data; this built-in admin is a
# low-level fallback for superusers.


@admin.register(User)
class AccountAdmin(UserAdmin):
    list_display = ['username', 'full_name', 'role', 'member_type', 'is_active']
    list_filter = ['role', 'member_type', 'is_active']
    fieldsets = UserAdmin.fieldsets + (
        ('Hồ sơ', {'fields': ['role', 'full_name', 'dob', 'phone', 'member_type', 'current_job',
                              'subjects']}),
    )


admin.site.register(Subject)
admin.site.register(Student)
admin.site.register(StudyClass, SimpleHistoryAdmin)
admin.site.register(ClassSession, SimpleHistoryAdmin)
admin.site.register(Attendance)
admin.site.register(ClassMaterial)
