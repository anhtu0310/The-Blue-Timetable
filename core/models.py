import datetime
import re
import unicodedata

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

MAX_STUDENTS_PER_CLASS = 10
WEEKDAY_NAMES = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ nhật']


def normalize(text):
    """Lowercase and strip Vietnamese accents, so a search for 'toan' matches 'Toán'."""
    text = (text or '').replace('đ', 'd').replace('Đ', 'D')
    text = unicodedata.normalize('NFD', text)
    return ''.join(c for c in text if unicodedata.category(c) != 'Mn').lower().strip()


class Subject(models.Model):
    """A subject tag. Used for teacher skills, student interests and class subjects."""

    name = models.CharField('Tên môn', max_length=100, unique=True)
    code = models.CharField('Mã môn', max_length=2, unique=True,
                            help_text='2 chữ cái, dùng làm tiền tố mã lớp (VD: TO = Toán).')
    search_name = models.CharField(max_length=100, editable=False, db_index=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Môn học'
        verbose_name_plural = 'Môn học'

    def __str__(self):
        return self.name

    def clean(self):
        self.code = (self.code or '').upper()
        if not re.fullmatch(r'[A-Z]{2}', self.code):
            raise ValidationError({'code': 'Mã môn phải gồm đúng 2 chữ cái (A-Z).'})

    def save(self, *args, **kwargs):
        self.code = self.code.upper()
        self.search_name = normalize(self.name)
        super().save(*args, **kwargs)


class User(AbstractUser):
    """A dashboard account. Only teachers/volunteers/staff have accounts."""

    class Role(models.TextChoices):
        TEACHER = 'teacher', 'Giáo viên'
        MODERATOR = 'moderator', 'Điều phối viên'
        ADMIN = 'admin', 'Quản trị viên'

    class MemberType(models.TextChoices):
        TEACHER = 'teacher', 'Giáo viên'
        VOLUNTEER = 'volunteer', 'Tình nguyện viên'

    role = models.CharField('Quyền tài khoản', max_length=10, choices=Role.choices, default=Role.TEACHER)
    full_name = models.CharField('Họ tên', max_length=150)
    dob = models.DateField('Ngày sinh', null=True, blank=True)
    phone = models.CharField('Số điện thoại', max_length=20, blank=True)
    member_type = models.CharField('Vai trò', max_length=10, choices=MemberType.choices,
                                   default=MemberType.TEACHER)
    current_job = models.CharField('Công việc hiện tại', max_length=150, blank=True)
    subjects = models.ManyToManyField(Subject, blank=True, related_name='teachers',
                                      verbose_name='Môn dạy')
    search_name = models.CharField(max_length=150, editable=False, db_index=True)

    class Meta:
        ordering = ['full_name', 'username']
        verbose_name = 'Tài khoản'
        verbose_name_plural = 'Tài khoản'

    def __str__(self):
        return self.full_name or self.username

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.Role.ADMIN
        self.search_name = normalize(self.full_name or self.username)
        super().save(*args, **kwargs)

    @property
    def is_moderator(self):
        """True for moderators and admins (admins have every moderator permission)."""
        return self.role in (self.Role.MODERATOR, self.Role.ADMIN)

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN


class Student(models.Model):
    full_name = models.CharField('Họ tên', max_length=150)
    dob = models.DateField('Ngày sinh', null=True, blank=True)
    social_worker_name = models.CharField('Tên nhân viên xã hội', max_length=150, blank=True)
    social_worker_phone = models.CharField('SĐT nhân viên xã hội', max_length=20, blank=True)
    subjects = models.ManyToManyField(Subject, blank=True, related_name='students',
                                      verbose_name='Môn quan tâm')
    search_name = models.CharField(max_length=150, editable=False, db_index=True)

    class Meta:
        ordering = ['full_name']
        verbose_name = 'Học sinh'
        verbose_name_plural = 'Học sinh'

    def __str__(self):
        return self.full_name

    def save(self, *args, **kwargs):
        self.search_name = normalize(self.full_name)
        super().save(*args, **kwargs)


class StudyClass(models.Model):
    class Status(models.TextChoices):
        ONGOING = 'ongoing', 'Đang diễn ra'
        PAUSED = 'paused', 'Tạm dừng'
        ENDED = 'ended', 'Đã kết thúc'

    class Frequency(models.TextChoices):
        WEEKLY = 'weekly', 'Hàng tuần'
        BIWEEKLY = 'biweekly', 'Hai tuần một lần'
        CUSTOM = 'custom', 'Ngày cụ thể'

    code = models.CharField('Mã lớp', max_length=6, unique=True, editable=False)
    number = models.PositiveSmallIntegerField(editable=False)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name='classes',
                                verbose_name='Môn học')
    grade = models.PositiveSmallIntegerField('Khối lớp', validators=[MaxValueValidator(99)])
    status = models.CharField('Trạng thái', max_length=10, choices=Status.choices, default=Status.ONGOING)
    teachers = models.ManyToManyField(User, blank=True, related_name='classes', verbose_name='Giáo viên')
    students = models.ManyToManyField(Student, blank=True, related_name='classes', verbose_name='Học sinh')
    room = models.CharField('Phòng học', max_length=50, blank=True)
    frequency = models.CharField('Tần suất', max_length=10, choices=Frequency.choices,
                                 default=Frequency.WEEKLY)
    # Comma separated weekday numbers (0 = Monday), used for weekly / bi-weekly classes.
    weekdays = models.CharField('Thứ trong tuần', max_length=20, blank=True)
    # Comma separated ISO dates, used for "custom" classes.
    custom_dates = models.TextField('Các ngày học', blank=True)
    start_date = models.DateField('Ngày bắt đầu', null=True, blank=True)
    end_date = models.DateField('Ngày kết thúc', null=True, blank=True)
    start_time = models.TimeField('Giờ bắt đầu')
    end_time = models.TimeField('Giờ kết thúc')
    note = models.TextField('Ghi chú', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords(m2m_fields=[teachers, students])

    class Meta:
        ordering = ['code']
        verbose_name = 'Lớp học'
        verbose_name_plural = 'Lớp học'

    def __str__(self):
        return f'{self.code} – {self.subject}'

    # --- class number -------------------------------------------------------

    def _code_needs_update(self):
        if not self.pk or not self.code:
            return True
        old = StudyClass.objects.filter(pk=self.pk).values('subject_id', 'grade').first()
        return old != {'subject_id': self.subject_id, 'grade': self.grade}

    def _next_free_number(self):
        used = set(StudyClass.objects.filter(subject_id=self.subject_id, grade=self.grade)
                   .exclude(pk=self.pk).values_list('number', flat=True))
        return next((n for n in range(100) if n not in used), None)

    def clean(self):
        if self.subject_id and self.grade is not None and self._code_needs_update():
            if self._next_free_number() is None:
                raise ValidationError('Đã dùng hết 100 mã lớp cho môn và khối này.')

    def save(self, *args, **kwargs):
        if self._code_needs_update():
            self.number = self._next_free_number()
            if self.number is None:
                raise ValidationError('Đã dùng hết 100 mã lớp cho môn và khối này.')
            self.code = f'{self.subject.code}{self.grade:02d}{self.number:02d}'
        super().save(*args, **kwargs)

    # --- schedule -----------------------------------------------------------

    @property
    def weekday_list(self):
        return sorted(int(d) for d in self.weekdays.split(',') if d.strip().isdigit())

    @property
    def custom_date_list(self):
        dates = []
        for part in re.split(r'[,\s]+', self.custom_dates or ''):
            try:
                dates.append(datetime.date.fromisoformat(part))
            except ValueError:
                pass
        return sorted(set(dates))

    def schedule_display(self):
        time = f'{self.start_time:%H:%M}–{self.end_time:%H:%M}'
        if self.frequency == self.Frequency.CUSTOM:
            days = ', '.join(f'{d:%d/%m/%Y}' for d in self.custom_date_list)
            return f'{time}, các ngày: {days}'
        days = ', '.join(WEEKDAY_NAMES[d] for d in self.weekday_list)
        period = ''
        if self.start_date and self.end_date:
            period = f' (từ {self.start_date:%d/%m/%Y} đến {self.end_date:%d/%m/%Y})'
        return f'{self.get_frequency_display()}: {days}, {time}{period}'

    def scheduled_dates(self):
        if self.frequency == self.Frequency.CUSTOM:
            return self.custom_date_list
        if not (self.start_date and self.end_date and self.weekday_list):
            return []
        step = 2 if self.frequency == self.Frequency.BIWEEKLY else 1
        first_monday = self.start_date - datetime.timedelta(days=self.start_date.weekday())
        days = set(self.weekday_list)
        dates, d = [], self.start_date
        while d <= self.end_date:
            if d.weekday() in days and ((d - first_monday).days // 7) % step == 0:
                dates.append(d)
            d += datetime.timedelta(days=1)
        return dates

    def sync_sessions(self, include_past=False):
        """Create, update and remove sessions so they match the class schedule.

        Sessions that are in the past, already submitted, or individually
        rescheduled are never touched. Past dates are only created when
        `include_past` is set (i.e. when the class is first created).
        """
        today = timezone.localdate()
        wanted = set(self.scheduled_dates()) if self.status == self.Status.ONGOING else set()
        existing = {s.original_date: s for s in self.sessions.all()}

        for original_date, session in existing.items():
            if original_date < today or session.is_locked or session.is_rescheduled:
                continue
            if original_date not in wanted:
                session.delete()
            elif (session.start_time, session.end_time, session.room) != (
                    self.start_time, self.end_time, self.room):
                session.start_time, session.end_time, session.room = (
                    self.start_time, self.end_time, self.room)
                session.save()

        for d in sorted(wanted - existing.keys()):
            if d < today and not include_past:
                continue
            ClassSession.objects.create(
                study_class=self, original_date=d, date=d,
                start_time=self.start_time, end_time=self.end_time, room=self.room)


class ClassMaterial(models.Model):
    study_class = models.ForeignKey(StudyClass, on_delete=models.CASCADE, related_name='materials')
    title = models.CharField('Tên tài liệu', max_length=200)
    url = models.URLField('Đường dẫn', max_length=500)
    added_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return self.title


class ClassSession(models.Model):
    study_class = models.ForeignKey(StudyClass, on_delete=models.CASCADE, related_name='sessions',
                                    verbose_name='Lớp')
    # The date the class schedule produced; stays fixed even if the session is moved.
    original_date = models.DateField()
    date = models.DateField('Ngày học')
    start_time = models.TimeField('Giờ bắt đầu')
    end_time = models.TimeField('Giờ kết thúc')
    room = models.CharField('Phòng học', max_length=50, blank=True)
    substitute_teacher = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='substitute_sessions',
        verbose_name='Giáo viên dạy thay')
    is_rescheduled = models.BooleanField('Đã điều chỉnh', default=False)
    is_cancelled = models.BooleanField('Hủy buổi học', default=False)
    change_reason = models.TextField('Lý do điều chỉnh', blank=True)
    teacher_comment = models.TextField('Nhận xét chung về buổi học', blank=True)
    submitted_at = models.DateTimeField('Thời điểm nộp', null=True, blank=True)
    submitted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name='+', verbose_name='Người nộp')

    history = HistoricalRecords()

    class Meta:
        ordering = ['date', 'start_time']
        constraints = [models.UniqueConstraint(fields=['study_class', 'original_date'],
                                               name='unique_session_per_class_date')]
        verbose_name = 'Buổi học'
        verbose_name_plural = 'Buổi học'

    def __str__(self):
        return f'{self.study_class.code} – {self.date:%d/%m/%Y}'

    @property
    def is_locked(self):
        """Submitted sessions can no longer be changed (only an admin can unlock them)."""
        return self.submitted_at is not None

    STATE_LABELS = {'cancelled': 'Đã hủy', 'done': 'Đã nộp', 'missing': 'Chưa nộp',
                    'changed': 'Đã điều chỉnh', 'planned': 'Sắp diễn ra'}

    @property
    def state(self):
        """One display state, used for colours in the calendar and lists."""
        if self.is_cancelled:
            return 'cancelled'
        if self.is_locked:
            return 'done'
        if self.date < timezone.localdate():
            return 'missing'
        return 'changed' if self.is_rescheduled else 'planned'

    @property
    def state_label(self):
        return self.STATE_LABELS[self.state]

    def teacher_list(self):
        if self.substitute_teacher_id:
            return [self.substitute_teacher]
        return list(self.study_class.teachers.all())


class Attendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = 'present', 'Có mặt'
        LATE = 'late', 'Đi muộn'
        EXCUSED = 'excused', 'Vắng có phép'
        ABSENT = 'absent', 'Vắng không phép'

    session = models.ForeignKey(ClassSession, on_delete=models.CASCADE, related_name='attendances')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendances')
    status = models.CharField('Điểm danh', max_length=10, choices=Status.choices, default=Status.PRESENT)
    feedback = models.TextField('Nhận xét', blank=True)

    class Meta:
        ordering = ['student__full_name']
        constraints = [models.UniqueConstraint(fields=['session', 'student'],
                                               name='unique_attendance_per_student')]

    def __str__(self):
        return f'{self.student} – {self.session}'
