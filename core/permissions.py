"""Who can see and do what. Every view goes through these helpers."""
from django.db.models import Q
from django.utils import timezone

from .models import ClassSession, Student, StudyClass


def visible_classes(user):
    qs = StudyClass.objects.select_related('subject')
    if user.is_moderator:
        return qs
    return qs.filter(Q(teachers=user) | Q(sessions__substitute_teacher=user)).distinct()


def visible_sessions(user):
    qs = ClassSession.objects.select_related('study_class__subject', 'substitute_teacher')
    if user.is_moderator:
        return qs
    return qs.filter(Q(study_class__teachers=user) | Q(substitute_teacher=user)).distinct()


def visible_students(user):
    if user.is_moderator:
        return Student.objects.all()
    return Student.objects.filter(classes__in=visible_classes(user)).distinct()


def can_view_teacher(user, teacher):
    return user.is_moderator or user.pk == teacher.pk


def is_session_teacher(user, session):
    return any(t.pk == user.pk for t in session.teacher_list())


def attendance_block_reason(user, session):
    """Why `user` cannot record attendance for `session`, or None if they can."""
    if not (user.is_moderator or is_session_teacher(user, session)):
        return 'Bạn không phụ trách buổi học này.'
    if session.is_locked:
        return 'Buổi học đã được nộp và không thể chỉnh sửa.'
    if session.is_cancelled:
        return 'Buổi học đã bị hủy.'
    if session.date > timezone.localdate():
        return 'Chỉ có thể điểm danh từ ngày diễn ra buổi học.'
    return None


def can_reschedule(user, session):
    return user.is_moderator and not session.is_locked
