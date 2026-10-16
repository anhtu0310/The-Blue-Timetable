import datetime

from django.core.management import call_command
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import ClassForm
from .history import describe_history
from .models import Attendance, ClassSession, Student, StudyClass, Subject, User, normalize

TODAY = timezone.localdate()


def make_class(subject, grade=6, **kwargs):
    defaults = dict(frequency='weekly', weekdays='0', start_date=TODAY - datetime.timedelta(days=14),
                    end_date=TODAY + datetime.timedelta(days=28),
                    start_time=datetime.time(17), end_time=datetime.time(18))
    defaults.update(kwargs)
    c = StudyClass.objects.create(subject=subject, grade=grade, **defaults)
    c.sync_sessions(include_past=True)
    return c


class ModelTests(TestCase):
    def setUp(self):
        self.maths = Subject.objects.create(name='Toán', code='to')

    def test_normalize_strips_vietnamese_accents(self):
        self.assertEqual(normalize('Tiếng Anh Đặc biệt'), 'tieng anh dac biet')

    def test_class_code_is_prefix_grade_and_counter(self):
        a = make_class(self.maths, grade=6)
        b = make_class(self.maths, grade=6)
        c = make_class(self.maths, grade=12)
        self.assertEqual([a.code, b.code, c.code], ['TO0600', 'TO0601', 'TO1200'])

    def test_class_code_reuses_free_number_and_updates_on_grade_change(self):
        a = make_class(self.maths, grade=6)
        make_class(self.maths, grade=6)
        a.grade = 7
        a.save()
        self.assertEqual(a.code, 'TO0700')
        self.assertEqual(make_class(self.maths, grade=6).code, 'TO0600')

    def test_weekly_and_biweekly_dates(self):
        monday = datetime.date(2026, 10, 5)
        c = StudyClass(subject=self.maths, grade=6, frequency='weekly', weekdays='0,2',
                       start_date=monday, end_date=monday + datetime.timedelta(days=13))
        self.assertEqual(len(c.scheduled_dates()), 4)
        c.frequency = 'biweekly'
        self.assertEqual(c.scheduled_dates(), [monday, monday + datetime.timedelta(days=2)])

    def test_sync_keeps_past_locked_and_rescheduled_sessions(self):
        c = make_class(self.maths)
        past = c.sessions.filter(date__lt=TODAY).first()
        future = list(c.sessions.filter(date__gt=TODAY))
        future[0].submitted_at = timezone.now()
        future[0].save()
        future[1].is_rescheduled = True
        future[1].save()

        c.status = StudyClass.Status.PAUSED
        c.sync_sessions()
        remaining = set(c.sessions.values_list('pk', flat=True))
        self.assertIn(past.pk, remaining)
        self.assertIn(future[0].pk, remaining)
        self.assertIn(future[1].pk, remaining)
        self.assertNotIn(future[2].pk, remaining)

    def test_sync_updates_time_of_future_sessions_only(self):
        c = make_class(self.maths)
        c.start_time, c.end_time = datetime.time(8), datetime.time(9)
        c.sync_sessions()
        self.assertTrue(all(s.start_time == datetime.time(17) for s in c.sessions.filter(date__lt=TODAY)))
        self.assertTrue(all(s.start_time == datetime.time(8) for s in c.sessions.filter(date__gte=TODAY)))


class ClassFormTests(TestCase):
    def setUp(self):
        self.maths = Subject.objects.create(name='Toán', code='TO')

    def data(self, **overrides):
        data = {'subject': self.maths.pk, 'grade': 6, 'status': 'ongoing', 'frequency': 'weekly',
                'weekdays': ['0'], 'start_date': '2026-10-01', 'end_date': '2026-12-01',
                'start_time': '17:00', 'end_time': '18:00'}
        data.update(overrides)
        return data

    def test_max_ten_students(self):
        students = [Student.objects.create(full_name=f'HS {i}') for i in range(11)]
        form = ClassForm(self.data(students=[s.pk for s in students]))
        self.assertFalse(form.is_valid())
        self.assertIn('students', form.errors)
        form = ClassForm(self.data(students=[s.pk for s in students[:10]]))
        self.assertTrue(form.is_valid(), form.errors)

    def test_custom_dates(self):
        form = ClassForm(self.data(frequency='custom', weekdays=[], start_date='', end_date='',
                                   custom_dates='2026-11-03, 2026-11-01'))
        self.assertTrue(form.is_valid(), form.errors)
        c = form.save()
        self.assertEqual(c.custom_dates, '2026-11-01, 2026-11-03')
        self.assertEqual(c.start_date, datetime.date(2026, 11, 1))

    def test_weekly_requires_weekdays_and_valid_times(self):
        form = ClassForm(self.data(weekdays=[], end_time='16:00'))
        self.assertFalse(form.is_valid())
        self.assertIn('weekdays', form.errors)
        self.assertIn('end_time', form.errors)


class PermissionTests(TestCase):
    def setUp(self):
        self.maths = Subject.objects.create(name='Toán', code='TO')
        self.admin = User.objects.create_user('admin', password='pw', full_name='Admin', role='admin')
        self.mod = User.objects.create_user('mod', password='pw', full_name='Mod', role='moderator')
        self.teacher = User.objects.create_user('t1', password='pw', full_name='Teacher One')
        self.other = User.objects.create_user('t2', password='pw', full_name='Teacher Two')
        self.student = Student.objects.create(full_name='Học Sinh')
        self.stranger = Student.objects.create(full_name='Người Lạ')
        self.c = make_class(self.maths)
        self.c.teachers.add(self.teacher)
        self.c.students.add(self.student)
        self.today_session = ClassSession.objects.create(
            study_class=self.c, original_date=TODAY + datetime.timedelta(days=100),
            date=TODAY, start_time=datetime.time(17), end_time=datetime.time(18))

    def login(self, user):
        self.client.force_login(user)

    def submit(self, session, status='absent'):
        return self.client.post(reverse('session_attendance', args=[session.pk]), {
            f'status_{self.student.pk}': status, f'feedback_{self.student.pk}': 'ok',
            'teacher_comment': 'good'})

    def test_teacher_sees_only_own_classes_and_students(self):
        self.login(self.other)
        self.assertEqual(self.client.get(reverse('class_detail', args=[self.c.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('student_detail', args=[self.student.pk])).status_code, 404)
        self.login(self.teacher)
        self.assertEqual(self.client.get(reverse('class_detail', args=[self.c.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('student_detail', args=[self.student.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('student_detail', args=[self.stranger.pk])).status_code, 404)
        events = self.client.get(reverse('calendar_events'), {'start': str(TODAY), 'end': str(
            TODAY + datetime.timedelta(days=1))}).json()
        self.assertIn(self.today_session.pk, [e['id'] for e in events])

    def test_teacher_cannot_manage(self):
        self.login(self.teacher)
        for name, args in [('class_create', []), ('class_edit', [self.c.pk]), ('teacher_list', []),
                           ('student_create', []), ('subject_list', []),
                           ('teacher_detail', [self.other.pk])]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 403, name)

    def test_moderator_manages_classes_but_not_accounts(self):
        self.login(self.mod)
        self.assertEqual(self.client.get(reverse('class_edit', args=[self.c.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('teacher_detail', args=[self.admin.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('teacher_create')).status_code, 403)
        self.assertEqual(self.client.get(reverse('student_create')).status_code, 403)

    def test_submit_locks_session(self):
        self.login(self.teacher)
        self.submit(self.today_session)
        self.today_session.refresh_from_db()
        self.assertTrue(self.today_session.is_locked)
        self.assertEqual(Attendance.objects.get().status, 'absent')

        # A second submit (teacher or moderator) changes nothing.
        self.submit(self.today_session, status='present')
        self.login(self.mod)
        self.submit(self.today_session, status='present')
        self.assertEqual(Attendance.objects.get().status, 'absent')
        response = self.client.post(reverse('session_reschedule', args=[self.today_session.pk]), {
            'date': str(TODAY), 'start_time': '08:00', 'end_time': '09:00', 'change_reason': 'x'})
        self.today_session.refresh_from_db()
        self.assertEqual(self.today_session.start_time, datetime.time(17))

        # Only an admin can unlock.
        self.assertEqual(self.client.post(reverse('session_unlock', args=[self.today_session.pk])).status_code, 403)
        self.login(self.admin)
        self.client.post(reverse('session_unlock', args=[self.today_session.pk]))
        self.today_session.refresh_from_db()
        self.assertFalse(self.today_session.is_locked)

    def test_cannot_submit_future_session_or_others_session(self):
        future = self.c.sessions.filter(date__gt=TODAY).first()
        self.login(self.teacher)
        self.submit(future)
        future.refresh_from_db()
        self.assertFalse(future.is_locked)
        self.login(self.other)
        self.assertEqual(self.submit(self.today_session).status_code, 404)

    def test_reschedule_one_session(self):
        self.login(self.mod)
        session = self.c.sessions.filter(date__gt=TODAY).first()
        self.client.post(reverse('session_reschedule', args=[session.pk]), {
            'date': str(session.date), 'start_time': '08:00', 'end_time': '09:00', 'room': 'B2',
            'substitute_teacher': self.other.pk, 'change_reason': 'Giáo viên ốm'})
        session.refresh_from_db()
        self.assertTrue(session.is_rescheduled)
        self.assertEqual(session.room, 'B2')
        # The substitute now sees the session; other sessions are unchanged.
        self.login(self.other)
        self.assertEqual(self.client.get(reverse('session_detail', args=[session.pk])).status_code, 200)
        self.assertEqual(self.c.sessions.filter(room='B2').count(), 1)

    def test_quick_status_change(self):
        url = reverse('class_status', args=[self.c.pk])
        future = self.c.sessions.filter(date__gt=TODAY, original_date__lte=TODAY + datetime.timedelta(days=28))
        past_count = self.c.sessions.filter(date__lt=TODAY).count()
        future_count = future.count()
        self.assertGreater(future_count, 0)

        self.login(self.teacher)
        self.assertEqual(self.client.post(url, {'status': 'paused'}).status_code, 403)

        self.login(self.mod)
        self.client.post(url, {'status': 'paused'})
        self.c.refresh_from_db()
        self.assertEqual(self.c.status, 'paused')
        self.assertEqual(future.count(), 0)
        self.assertEqual(self.c.sessions.filter(date__lt=TODAY).count(), past_count)

        self.client.post(url, {'status': 'ongoing'})
        self.assertEqual(future.count(), future_count)

        self.client.post(url, {'status': 'bogus'})
        self.c.refresh_from_db()
        self.assertEqual(self.c.status, 'ongoing')
        changed = [label for h in describe_history(self.c) for label, *_ in h['changes']]
        self.assertIn('Trạng thái', changed)

    def test_month_stats(self):
        self.login(self.teacher)
        self.submit(self.today_session)
        response = self.client.get(reverse('calendar_stats'), {'month': TODAY.strftime('%Y-%m')})
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        self.assertEqual(ctx['done'], 1)
        self.assertEqual(ctx['att_total'], 1)
        self.assertEqual(ctx['attend_rate'], 0)  # the one student was marked absent
        self.assertEqual([r['c'] for r in ctx['rows']], [self.c])
        # Another teacher sees nothing for this class.
        self.login(self.other)
        response = self.client.get(reverse('calendar_stats'), {'month': TODAY.strftime('%Y-%m')})
        self.assertEqual(response.context['total'], 0)
        # A bad month falls back to the current one instead of failing.
        self.assertEqual(self.client.get(reverse('calendar_stats'), {'month': 'abc'}).status_code, 200)

    def test_search_by_partial_unaccented_tag(self):
        english = Subject.objects.create(name='Tiếng Anh', code='TA')
        self.other.subjects.add(english)
        self.login(self.mod)
        response = self.client.get(reverse('teacher_list'), {'q': 'tieng an'})
        self.assertEqual([p.pk for p in response.context['people']], [self.other.pk])

    def test_admin_cannot_demote_self(self):
        self.login(self.admin)
        self.client.post(reverse('teacher_edit', args=[self.admin.pk]), {
            'username': 'admin', 'full_name': 'Admin', 'member_type': 'teacher', 'role': 'teacher',
            'is_active': 'on'})
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, 'admin')


class SmokeTests(TestCase):
    """Every page renders for every role on the demo data."""

    @classmethod
    def setUpTestData(cls):
        call_command('seed_demo', stdout=open('/dev/null', 'w'))

    def test_pages_render(self):
        c = StudyClass.objects.get(teachers__username='gv.lan')
        session = c.sessions.first()
        student = c.students.first()
        for username in ['admin', 'dieuphoi', 'gv.lan']:
            user = User.objects.get(username=username)
            self.client.force_login(user)
            urls = [reverse('calendar'), reverse('class_list'), reverse('student_list'),
                    reverse('class_detail', args=[c.pk]), reverse('session_detail', args=[session.pk]),
                    reverse('student_detail', args=[student.pk]), reverse('me'),
                    reverse('password_change')]
            if user.is_moderator:
                urls += [reverse('teacher_list'), reverse('subject_list'), reverse('class_create'),
                         reverse('class_edit', args=[c.pk]),
                         reverse('session_reschedule', args=[c.sessions.last().pk])]
            for url in urls:
                response = self.client.get(url, follow=True)
                self.assertEqual(response.status_code, 200, f'{username} {url}')
                response = self.client.get(url, follow=True, headers={'HX-Request': 'true'})
                self.assertEqual(response.status_code, 200, f'{username} {url} (htmx)')


class SecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user('t1', password='right-password', full_name='Teacher')

    def test_login_locks_after_repeated_failures(self):
        url = reverse('login')
        for _ in range(5):
            self.client.post(url, {'username': 't1', 'password': 'wrong'})
        response = self.client.post(url, {'username': 't1', 'password': 'right-password'})
        self.assertContains(response, 'quá nhiều lần')
        self.assertNotIn('_auth_user_id', self.client.session)

    @override_settings(DEMO_MODE=True)
    def test_demo_mode_blocks_password_change(self):
        self.client.post(reverse('login'), {'username': 't1', 'password': 'right-password'})
        response = self.client.post(reverse('password_change'), {
            'old_password': 'right-password', 'new_password1': 'N3w-pass-123!', 'new_password2': 'N3w-pass-123!'})
        self.assertRedirects(response, reverse('calendar'))
        self.assertTrue(User.objects.get(username='t1').check_password('right-password'))
