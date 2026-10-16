import datetime
import re

from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.cache import cache

from .models import (MAX_STUDENTS_PER_CLASS, WEEKDAY_NAMES, Attendance, ClassMaterial, ClassSession,
                     Student, StudyClass, Subject, User)

DATE_INPUT = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')
TIME_INPUT = forms.TimeInput(attrs={'type': 'time'}, format='%H:%M')
CHECKBOXES = forms.CheckboxSelectMultiple(attrs={'class': 'checks'})


class ThrottledLoginForm(AuthenticationForm):
    """Login form that locks a username for a while after repeated wrong passwords from one address."""

    locked = False

    def _key(self):
        username = (self.data.get('username') or '').strip().lower()
        return f'login-failures:{username}:{self.request.META.get("REMOTE_ADDR", "")}'

    def clean(self):
        key = self._key()
        if cache.get(key, 0) >= settings.LOGIN_MAX_FAILURES:
            self.locked = True
            raise forms.ValidationError('Đăng nhập sai quá nhiều lần. Vui lòng thử lại sau 15 phút.',
                                        code='locked')
        try:
            return super().clean()
        except forms.ValidationError:
            cache.set(key, cache.get(key, 0) + 1, settings.LOGIN_LOCK_SECONDS)
            raise


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['name', 'code']


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ['full_name', 'dob', 'social_worker_name', 'social_worker_phone', 'subjects']
        widgets = {'dob': DATE_INPUT, 'subjects': CHECKBOXES}


ACCOUNT_FIELDS = ['username', 'full_name', 'dob', 'phone', 'member_type', 'current_job', 'subjects',
                  'role', 'is_active']
ACCOUNT_WIDGETS = {'dob': DATE_INPUT, 'subjects': CHECKBOXES}


class AccountCreateForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ACCOUNT_FIELDS
        widgets = ACCOUNT_WIDGETS


class AccountEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ACCOUNT_FIELDS
        widgets = ACCOUNT_WIDGETS

    def __init__(self, *args, editor, **kwargs):
        super().__init__(*args, **kwargs)
        self.editor = editor

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk == self.editor.pk and (
                cleaned.get('role') != User.Role.ADMIN or not cleaned.get('is_active')):
            raise forms.ValidationError(
                'Bạn không thể tự gỡ quyền quản trị hoặc khóa tài khoản của chính mình.')
        return cleaned


class ClassForm(forms.ModelForm):
    weekdays = forms.TypedMultipleChoiceField(
        label='Thứ trong tuần', choices=list(enumerate(WEEKDAY_NAMES)), coerce=int,
        required=False, widget=CHECKBOXES)

    class Meta:
        model = StudyClass
        fields = ['subject', 'grade', 'status', 'room', 'frequency', 'start_date', 'end_date',
                  'custom_dates', 'start_time', 'end_time', 'teachers', 'students', 'note']
        widgets = {
            'start_date': DATE_INPUT, 'end_date': DATE_INPUT,
            'start_time': TIME_INPUT, 'end_time': TIME_INPUT,
            'custom_dates': forms.TextInput(attrs={'data-multidate': '', 'autocomplete': 'off'}),
            'teachers': CHECKBOXES, 'students': CHECKBOXES,
            'note': forms.Textarea(attrs={'rows': 2}),
        }
        help_texts = {'grade': 'VD: 6 cho lớp 6.'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial['weekdays'] = self.instance.weekday_list
        self.fields['teachers'].queryset = User.objects.filter(is_active=True).prefetch_related('subjects')
        self.fields['students'].queryset = Student.objects.prefetch_related('subjects')

    def clean_students(self):
        students = self.cleaned_data['students']
        if len(students) > MAX_STUDENTS_PER_CLASS:
            raise forms.ValidationError(f'Mỗi lớp tối đa {MAX_STUDENTS_PER_CLASS} học sinh '
                                        f'(đang chọn {len(students)}).')
        return students

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('frequency') == StudyClass.Frequency.CUSTOM:
            dates = []
            for part in re.split(r'[,\s]+', cleaned.get('custom_dates') or ''):
                if not part:
                    continue
                try:
                    dates.append(datetime.date.fromisoformat(part))
                except ValueError:
                    self.add_error('custom_dates', f'Ngày không hợp lệ: {part}')
            dates = sorted(set(dates))
            if not dates and 'custom_dates' not in self.errors:
                self.add_error('custom_dates', 'Hãy chọn ít nhất một ngày học.')
            if dates:
                cleaned['custom_dates'] = ', '.join(d.isoformat() for d in dates)
                cleaned['start_date'], cleaned['end_date'] = dates[0], dates[-1]
            self.instance.weekdays = ''
        else:
            if not cleaned.get('weekdays'):
                self.add_error('weekdays', 'Hãy chọn ít nhất một ngày trong tuần.')
            if not cleaned.get('start_date'):
                self.add_error('start_date', 'Hãy nhập ngày bắt đầu.')
            if not cleaned.get('end_date'):
                self.add_error('end_date', 'Hãy nhập ngày kết thúc.')
            start, end = cleaned.get('start_date'), cleaned.get('end_date')
            if start and end and end < start:
                self.add_error('end_date', 'Ngày kết thúc phải sau ngày bắt đầu.')
            cleaned['custom_dates'] = ''
            self.instance.weekdays = ','.join(str(d) for d in sorted(cleaned.get('weekdays') or []))

        start_time, end_time = cleaned.get('start_time'), cleaned.get('end_time')
        if start_time and end_time and end_time <= start_time:
            self.add_error('end_time', 'Giờ kết thúc phải sau giờ bắt đầu.')
        return cleaned


class RescheduleForm(forms.ModelForm):
    class Meta:
        model = ClassSession
        fields = ['date', 'start_time', 'end_time', 'room', 'substitute_teacher', 'is_cancelled',
                  'change_reason']
        widgets = {'date': DATE_INPUT, 'start_time': TIME_INPUT, 'end_time': TIME_INPUT,
                   'change_reason': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['substitute_teacher'].queryset = User.objects.filter(is_active=True)
        self.fields['substitute_teacher'].empty_label = '— Giữ giáo viên của lớp —'
        self.fields['change_reason'].required = True

    def clean(self):
        cleaned = super().clean()
        start_time, end_time = cleaned.get('start_time'), cleaned.get('end_time')
        if start_time and end_time and end_time <= start_time:
            self.add_error('end_time', 'Giờ kết thúc phải sau giờ bắt đầu.')
        return cleaned


class AttendanceForm(forms.Form):
    """One status + feedback pair per student, plus a general comment on the session."""

    teacher_comment = forms.CharField(label='Nhận xét chung về buổi học', required=False,
                                      widget=forms.Textarea(attrs={'rows': 2}))

    def __init__(self, *args, students, **kwargs):
        super().__init__(*args, **kwargs)
        self.students = list(students)
        for s in self.students:
            self.fields[f'status_{s.pk}'] = forms.ChoiceField(
                label=s.full_name, choices=Attendance.Status.choices, initial=Attendance.Status.PRESENT)
            self.fields[f'feedback_{s.pk}'] = forms.CharField(
                label='Nhận xét', required=False, widget=forms.Textarea(attrs={'rows': 1}))

    def rows(self):
        for s in self.students:
            yield s, self[f'status_{s.pk}'], self[f'feedback_{s.pk}']


class MaterialForm(forms.ModelForm):
    class Meta:
        model = ClassMaterial
        fields = ['title', 'url']
        widgets = {'url': forms.URLInput(attrs={'placeholder': 'https://...'})}
