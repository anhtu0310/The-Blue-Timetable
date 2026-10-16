import datetime
from collections import Counter
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, ProtectedError, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from .forms import (AccountCreateForm, AccountEditForm, AttendanceForm, ClassForm, MaterialForm,
                    RescheduleForm, StudentForm, SubjectForm)
from .history import describe_history
from .models import Attendance, ClassMaterial, ClassSession, Student, StudyClass, Subject, User, normalize
from .permissions import (attendance_block_reason, can_reschedule, can_view_teacher, is_session_teacher,
                          visible_classes, visible_sessions, visible_students)


# --- helpers -----------------------------------------------------------------

def moderator_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_moderator:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapper


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_admin:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapper


def page(request, template, context=None):
    """Render a full page, or just the content when loaded into the pop-up by HTMX."""
    context = context or {}
    context['base_template'] = 'core/partial.html' if request.htmx else 'core/base.html'
    return render(request, template, context)


def form_page(request, form, title, submit='Lưu', cancel_url=None, danger=None):
    return page(request, 'core/form_page.html', {
        'form': form, 'title': title, 'submit': submit, 'cancel_url': cancel_url, 'danger': danger})


def confirm_delete(request, obj, cancel_url, warning=''):
    return page(request, 'core/confirm_delete.html', {
        'object': obj, 'cancel_url': cancel_url, 'warning': warning})


def search_people(qs, request):
    """Filter teachers/students by name or subject tag; partial and accent-insensitive."""
    tag = request.GET.get('tag')
    q = request.GET.get('q', '').strip()
    if tag:
        qs = qs.filter(subjects__pk=tag)
    if q:
        n = normalize(q)
        qs = qs.filter(Q(search_name__contains=n) | Q(subjects__search_name__contains=n))
    return qs.distinct().prefetch_related('subjects')


# --- calendar ----------------------------------------------------------------

@login_required
def calendar(request):
    user = request.user
    today = timezone.localdate()
    week_start = today - datetime.timedelta(days=today.weekday())
    sessions = visible_sessions(user)
    pending = sessions.filter(date__lt=today, submitted_at__isnull=True, is_cancelled=False).order_by('-date')
    return render(request, 'core/calendar.html', {
        'today_sessions': sessions.filter(date=today).order_by('start_time'),
        'week_count': sessions.filter(date__range=(week_start, week_start + datetime.timedelta(days=6)),
                                      is_cancelled=False).count(),
        'pending_count': pending.count(),
        'pending': pending[:6],
        'active_classes': visible_classes(user).filter(status=StudyClass.Status.ONGOING).count(),
    })


@login_required
def month_stats(request):
    """Statistics for the month the calendar is showing (`?month=YYYY-MM`)."""
    user = request.user
    today = timezone.localdate()
    try:
        first = datetime.date.fromisoformat(request.GET.get('month', '') + '-01')
    except ValueError:
        first = today.replace(day=1)
    next_first = (first + datetime.timedelta(days=32)).replace(day=1)
    mine = request.GET.get('mine') == '1'
    sessions = visible_sessions(user).filter(date__gte=first, date__lt=next_first)
    if mine:
        sessions = sessions.filter(Q(study_class__teachers=user) | Q(substitute_teacher=user)).distinct()
    sessions = list(sessions)
    states = Counter(s.state for s in sessions)
    due = states['done'] + states['missing']
    ids = [s.pk for s in sessions]

    attendance = Attendance.objects.filter(session_id__in=ids)
    counts = Counter(dict(attendance.values_list('status').annotate(n=Count('id'))))
    att_total = sum(counts.values())
    segments = [{'key': key, 'label': label, 'count': counts[key],
                 'pct': round(100 * counts[key] / att_total) if att_total else 0}
                for key, label in Attendance.Status.choices]

    per_class = {}
    for s in sessions:
        row = per_class.setdefault(s.study_class_id, {'c': s.study_class, 'total': 0, 'done': 0,
                                                      'attended': 0, 'records': 0})
        if not s.is_cancelled:
            row['total'] += 1
            row['done'] += s.is_locked
    for class_id, status, n in (attendance.values_list('session__study_class_id', 'status')
                                .annotate(n=Count('id'))):
        per_class[class_id]['records'] += n
        if status in (Attendance.Status.PRESENT, Attendance.Status.LATE):
            per_class[class_id]['attended'] += n
    rows = sorted(per_class.values(), key=lambda r: r['c'].code)
    for row in rows:
        row['rate'] = round(100 * row['attended'] / row['records']) if row['records'] else None

    submit_rate = round(100 * states['done'] / due) if due else None
    return render(request, 'core/_month_stats.html', {
        'first': first,
        'mine': mine,
        'total': len(sessions) - states['cancelled'],
        'done': states['done'],
        'missing': states['missing'],
        'upcoming': states['planned'] + states['changed'],
        'cancelled': states['cancelled'],
        'due': due,
        'submit_rate': submit_rate,
        'submit_tone': 'good' if submit_rate is None or submit_rate >= 80 else
                       'warning' if submit_rate >= 50 else 'critical',
        'att_total': att_total,
        'attend_rate': round(100 * (counts['present'] + counts['late']) / att_total) if att_total else None,
        'segments': segments,
        'rows': rows,
    })


@login_required
def calendar_events(request):
    start = parse_date(request.GET.get('start', '')[:10])
    end = parse_date(request.GET.get('end', '')[:10])
    if not (start and end):
        return JsonResponse([], safe=False)
    sessions = visible_sessions(request.user).filter(date__gte=start, date__lt=end)
    if request.GET.get('mine') == '1':
        user = request.user
        sessions = sessions.filter(Q(study_class__teachers=user) | Q(substitute_teacher=user)).distinct()

    events = []
    for s in sessions:
        c = s.study_class
        events.append({
            'id': s.pk,
            'title': f'{c.code} · {c.subject.name}' + (f' · P.{s.room}' if s.room else ''),
            'start': datetime.datetime.combine(s.date, s.start_time).isoformat(),
            'end': datetime.datetime.combine(s.date, s.end_time).isoformat(),
            'classNames': [f'ev-{s.state}'],
            'extendedProps': {'url': reverse('session_detail', args=[s.pk]), 'code': c.code,
                              'subject': c.subject.name, 'room': s.room},
        })
    return JsonResponse(events, safe=False)


# --- sessions ----------------------------------------------------------------

def render_session(request, session, form=None, changed=False):
    user = request.user
    block_reason = attendance_block_reason(user, session)
    if form is None and block_reason is None:
        form = AttendanceForm(students=session.study_class.students.all(),
                              initial={'teacher_comment': session.teacher_comment})
    c = session.study_class
    response = page(request, 'core/session_detail.html', {
        'session': session,
        'c': c,
        'form': form,
        'block_reason': block_reason,
        'can_see_results': user.is_moderator or is_session_teacher(user, session)
                           or c.teachers.filter(pk=user.pk).exists(),
        'can_reschedule': can_reschedule(user, session),
        'attendances': session.attendances.select_related('student'),
        'history': describe_history(session) if user.is_moderator else None,
    })
    if changed:
        response['HX-Trigger'] = 'calendarChanged'
    return response


def after_session_change(request, session):
    if request.htmx:
        session.refresh_from_db()
        return render_session(request, session, changed=True)
    return redirect('session_detail', pk=session.pk)


@login_required
def session_detail(request, pk):
    session = get_object_or_404(visible_sessions(request.user), pk=pk)
    return render_session(request, session)


@login_required
@require_POST
def session_attendance(request, pk):
    session = get_object_or_404(visible_sessions(request.user), pk=pk)
    reason = attendance_block_reason(request.user, session)
    if reason:
        messages.error(request, reason)
        return after_session_change(request, session)

    form = AttendanceForm(request.POST, students=session.study_class.students.all())
    if not form.is_valid():
        return render_session(request, session, form=form)

    with transaction.atomic():
        # Re-check inside the transaction so a double click cannot submit twice.
        session = ClassSession.objects.select_for_update().get(pk=session.pk)
        if session.is_locked:
            messages.error(request, 'Buổi học đã được nộp trước đó.')
            return after_session_change(request, session)
        for student, status, feedback in form.rows():
            Attendance.objects.update_or_create(
                session=session, student=student,
                defaults={'status': status.value(), 'feedback': feedback.value() or ''})
        session.teacher_comment = form.cleaned_data['teacher_comment']
        session.submitted_at = timezone.now()
        session.submitted_by = request.user
        session.save()
    messages.success(request, 'Đã nộp điểm danh và nhận xét.')
    return after_session_change(request, session)


@moderator_required
def session_reschedule(request, pk):
    session = get_object_or_404(ClassSession, pk=pk)
    if not can_reschedule(request.user, session):
        messages.error(request, 'Buổi học đã được nộp nên không thể điều chỉnh.')
        return after_session_change(request, session)
    form = RescheduleForm(request.POST or None, instance=session)
    if request.method == 'POST' and form.is_valid():
        session = form.save(commit=False)
        session.is_rescheduled = True
        session.save()
        messages.success(request, 'Đã điều chỉnh buổi học.')
        return after_session_change(request, session)
    return page(request, 'core/session_reschedule.html', {'form': form, 'session': session})


@admin_required
@require_POST
def session_unlock(request, pk):
    session = get_object_or_404(ClassSession, pk=pk)
    session.submitted_at = None
    session.submitted_by = None
    session.save()
    messages.success(request, 'Đã mở khóa buổi học. Giáo viên có thể nộp lại.')
    return after_session_change(request, session)


# --- classes -----------------------------------------------------------------

@login_required
def class_list(request):
    classes = visible_classes(request.user).prefetch_related('teachers').annotate(
        student_count=Count('students', distinct=True))
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    if q:
        n = normalize(q)
        classes = classes.filter(Q(code__icontains=q) | Q(subject__search_name__contains=n) |
                                 Q(room__icontains=q) | Q(teachers__search_name__contains=n))
    if status:
        classes = classes.filter(status=status)
    return render(request, 'core/class_list.html', {
        'classes': classes.distinct(), 'q': q, 'status': status, 'statuses': StudyClass.Status.choices})


@login_required
def class_detail(request, pk):
    c = get_object_or_404(visible_classes(request.user), pk=pk)
    user = request.user
    is_teacher = c.teachers.filter(pk=user.pk).exists()
    sessions = c.sessions.select_related('substitute_teacher')
    if not (user.is_moderator or is_teacher):
        sessions = sessions.filter(substitute_teacher=user)
    today = timezone.localdate()
    next_session = sessions.filter(date__gte=today).first()
    return page(request, 'core/class_detail.html', {
        'c': c,
        'sessions': sessions,
        'next_session_id': next_session.pk if next_session else None,
        'can_add_material': user.is_moderator or is_teacher,
        'material_form': MaterialForm(),
        'history': describe_history(c) if user.is_moderator else None,
        'today': today,
    })


def save_class(form):
    is_new = form.instance.pk is None
    with transaction.atomic():
        c = form.save()
        c.save()  # snapshot teacher/student lists into the change history
        c.sync_sessions(include_past=is_new)
    return c


@moderator_required
def class_create(request):
    form = ClassForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        c = save_class(form)
        messages.success(request, f'Đã tạo lớp {c.code} với {c.sessions.count()} buổi học.')
        return redirect('class_detail', pk=c.pk)
    return page(request, 'core/class_form.html', {'form': form, 'subjects': Subject.objects.all()})


@moderator_required
def class_edit(request, pk):
    c = get_object_or_404(StudyClass, pk=pk)
    session_id = request.GET.get('session')
    form = ClassForm(request.POST or None, instance=c)
    if request.method == 'POST' and form.is_valid():
        c = save_class(form)
        messages.success(request, f'Đã cập nhật lớp {c.code}.')
        return after_class_change(request, c, session_id)
    return page(request, 'core/class_form.html', {
        'form': form, 'c': c, 'session_id': session_id, 'subjects': Subject.objects.all()})


def after_class_change(request, c, session_id=None):
    """Back to the session pop-up the change was made from, else to the class page."""
    if not request.htmx:
        return redirect('class_detail', pk=c.pk)
    session = ClassSession.objects.filter(pk=session_id).first() if session_id else None
    if session:
        return render_session(request, session, changed=True)
    if session_id:
        messages.info(request, 'Buổi học vừa xem đã bị xóa do thay đổi lịch.')
    response = class_detail(request, c.pk)
    response['HX-Trigger'] = 'calendarChanged'
    return response


@moderator_required
@require_POST
def class_status(request, pk):
    """Quick switch between ongoing / paused / ended without opening the full form."""
    c = get_object_or_404(StudyClass, pk=pk)
    status = request.POST.get('status')
    if status not in StudyClass.Status.values:
        messages.error(request, 'Trạng thái không hợp lệ.')
    elif status != c.status:
        before = c.sessions.count()
        with transaction.atomic():
            c.status = status
            c.save()
            c.sync_sessions()
        change = c.sessions.count() - before
        message = f'Lớp {c.code} đã chuyển sang “{c.get_status_display()}”.'
        if change < 0:
            message += f' Đã xóa {-change} buổi học sắp tới chưa nộp.'
        elif change > 0:
            message += f' Đã tạo lại {change} buổi học sắp tới theo lịch.'
        messages.success(request, message)
    return after_class_change(request, c, request.GET.get('session'))


@admin_required
def class_delete(request, pk):
    c = get_object_or_404(StudyClass, pk=pk)
    if request.method == 'POST':
        c.delete()
        messages.success(request, f'Đã xóa lớp {c.code}.')
        return redirect('class_list')
    return confirm_delete(request, c, reverse('class_detail', args=[pk]),
                          'Toàn bộ buổi học, điểm danh và nhận xét của lớp cũng sẽ bị xóa.')


@login_required
@require_POST
def material_add(request, pk):
    c = get_object_or_404(visible_classes(request.user), pk=pk)
    if not (request.user.is_moderator or c.teachers.filter(pk=request.user.pk).exists()):
        raise PermissionDenied
    form = MaterialForm(request.POST)
    if form.is_valid():
        material = form.save(commit=False)
        material.study_class = c
        material.added_by = request.user
        material.save()
        messages.success(request, 'Đã thêm tài liệu.')
    else:
        messages.error(request, 'Tài liệu không hợp lệ: hãy nhập tên và đường dẫn bắt đầu bằng http(s)://')
    return redirect('class_detail', pk=pk)


@login_required
@require_POST
def material_delete(request, pk):
    material = get_object_or_404(ClassMaterial, pk=pk)
    if not (request.user.is_moderator or material.added_by_id == request.user.pk):
        raise PermissionDenied
    material.delete()
    messages.success(request, 'Đã xóa tài liệu.')
    return redirect('class_detail', pk=material.study_class_id)


# --- teachers (accounts) -----------------------------------------------------

def no_demo_password_change(view):
    """In the public demo, passwords stay as published so visitors cannot lock each other out."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if settings.DEMO_MODE:
            messages.info(request, 'Đổi mật khẩu đã bị tắt trong bản demo.')
            return redirect('calendar')
        return view(request, *args, **kwargs)
    return wrapper


password_change = login_required(no_demo_password_change(auth_views.PasswordChangeView.as_view(
    template_name='core/password_change.html', success_url='/')))


@login_required
def me(request):
    return redirect('teacher_detail', pk=request.user.pk)


@moderator_required
def teacher_list(request):
    teachers = search_people(User.objects.all(), request)
    return render(request, 'core/teacher_list.html', {
        'people': teachers, 'q': request.GET.get('q', ''), 'tag': request.GET.get('tag', ''),
        'subjects': Subject.objects.all()})


@login_required
def teacher_detail(request, pk):
    teacher = get_object_or_404(User, pk=pk)
    if not can_view_teacher(request.user, teacher):
        raise PermissionDenied
    upcoming = (ClassSession.objects
                .filter(Q(study_class__teachers=teacher) | Q(substitute_teacher=teacher),
                        date__gte=timezone.localdate(), is_cancelled=False)
                .select_related('study_class__subject').distinct()[:10])
    return render(request, 'core/teacher_detail.html', {
        'person': teacher, 'classes': teacher.classes.select_related('subject'), 'upcoming': upcoming})


@admin_required
def teacher_create(request):
    form = AccountCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        teacher = form.save()
        messages.success(request, f'Đã tạo tài khoản {teacher.username}.')
        return redirect('teacher_detail', pk=teacher.pk)
    return form_page(request, form, 'Tạo tài khoản giáo viên', cancel_url=reverse('teacher_list'))


@admin_required
def teacher_edit(request, pk):
    teacher = get_object_or_404(User, pk=pk)
    form = AccountEditForm(request.POST or None, instance=teacher, editor=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Đã lưu hồ sơ.')
        return redirect('teacher_detail', pk=pk)
    return form_page(request, form, f'Sửa hồ sơ: {teacher}', cancel_url=reverse('teacher_detail', args=[pk]))


@admin_required
@no_demo_password_change
def teacher_password(request, pk):
    teacher = get_object_or_404(User, pk=pk)
    form = SetPasswordForm(teacher, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Đã đặt mật khẩu mới cho {teacher}.')
        return redirect('teacher_detail', pk=pk)
    return form_page(request, form, f'Đặt lại mật khẩu: {teacher}',
                     cancel_url=reverse('teacher_detail', args=[pk]))


@admin_required
def teacher_delete(request, pk):
    teacher = get_object_or_404(User, pk=pk)
    if teacher.pk == request.user.pk:
        messages.error(request, 'Bạn không thể xóa tài khoản của chính mình.')
        return redirect('teacher_detail', pk=pk)
    if request.method == 'POST':
        teacher.delete()
        messages.success(request, f'Đã xóa tài khoản {teacher}.')
        return redirect('teacher_list')
    return confirm_delete(request, teacher, reverse('teacher_detail', args=[pk]),
                          'Giáo viên sẽ bị gỡ khỏi các lớp đang dạy. Có thể chọn "khóa tài khoản" '
                          'trong phần sửa hồ sơ thay vì xóa.')


# --- students ----------------------------------------------------------------

@login_required
def student_list(request):
    students = search_people(visible_students(request.user), request)
    return render(request, 'core/student_list.html', {
        'people': students, 'q': request.GET.get('q', ''), 'tag': request.GET.get('tag', ''),
        'subjects': Subject.objects.all()})


@login_required
def student_detail(request, pk):
    student = get_object_or_404(visible_students(request.user), pk=pk)
    sessions = visible_sessions(request.user)
    return render(request, 'core/student_detail.html', {
        'person': student,
        'classes': student.classes.filter(pk__in=visible_classes(request.user).values('pk')),
        'attendances': (Attendance.objects.filter(student=student, session__in=sessions)
                        .select_related('session__study_class__subject')
                        .order_by('-session__date')),
    })


@admin_required
def student_create(request):
    form = StudentForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        student = form.save()
        messages.success(request, f'Đã thêm học sinh {student}.')
        return redirect('student_detail', pk=student.pk)
    return form_page(request, form, 'Thêm học sinh', cancel_url=reverse('student_list'))


@admin_required
def student_edit(request, pk):
    student = get_object_or_404(Student, pk=pk)
    form = StudentForm(request.POST or None, instance=student)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Đã lưu hồ sơ học sinh.')
        return redirect('student_detail', pk=pk)
    return form_page(request, form, f'Sửa hồ sơ: {student}', cancel_url=reverse('student_detail', args=[pk]))


@admin_required
def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        student.delete()
        messages.success(request, f'Đã xóa học sinh {student}.')
        return redirect('student_list')
    return confirm_delete(request, student, reverse('student_detail', args=[pk]),
                          'Toàn bộ điểm danh và nhận xét của học sinh này cũng sẽ bị xóa.')


# --- subjects ----------------------------------------------------------------

@moderator_required
def subject_list(request):
    form = SubjectForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        subject = form.save()
        messages.success(request, f'Đã thêm môn {subject}.')
        return redirect('subject_list')
    subjects = Subject.objects.annotate(
        teacher_count=Count('teachers', distinct=True), student_count=Count('students', distinct=True),
        class_count=Count('classes', distinct=True))
    return render(request, 'core/subject_list.html', {'subjects': subjects, 'form': form})


@moderator_required
def subject_edit(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    form = SubjectForm(request.POST or None, instance=subject)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Đã lưu môn học. Mã lớp cũ được giữ nguyên.')
        return redirect('subject_list')
    return form_page(request, form, f'Sửa môn: {subject}', cancel_url=reverse('subject_list'))


@moderator_required
def subject_delete(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    if request.method == 'POST':
        try:
            subject.delete()
            messages.success(request, f'Đã xóa môn {subject}.')
        except ProtectedError:
            messages.error(request, f'Không thể xóa môn {subject} vì đang có lớp học thuộc môn này.')
        return redirect('subject_list')
    return confirm_delete(request, subject, reverse('subject_list'))
