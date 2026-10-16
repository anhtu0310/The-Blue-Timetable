import datetime
import random

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import Attendance, ClassMaterial, Student, StudyClass, Subject, User

SUBJECTS = [('Toán', 'TO'), ('Tiếng Anh', 'TA'), ('Ngữ văn', 'NV'), ('Vật lý', 'VL'), ('Hóa học', 'HH'),
            ('Sinh học', 'SH'), ('Tin học', 'TH'), ('Lịch sử', 'LS'), ('Địa lý', 'DL'), ('Kỹ năng sống', 'KN')]

ACCOUNTS = [
    # username, full name, role, member type, job, subjects
    ('admin', 'Quản trị viên', User.Role.ADMIN, User.MemberType.TEACHER, 'Điều phối L&D', []),
    ('dieuphoi', 'Trần Thu Hà', User.Role.MODERATOR, User.MemberType.TEACHER, 'Nhân viên L&D', ['NV', 'KN']),
    ('gv.lan', 'Nguyễn Thị Lan', User.Role.TEACHER, User.MemberType.TEACHER, 'Giáo viên THCS', ['TO', 'VL']),
    ('gv.minh', 'Lê Văn Minh', User.Role.TEACHER, User.MemberType.TEACHER, 'Kỹ sư phần mềm', ['TH', 'TO']),
    ('tnv.anna', 'Anna Smith', User.Role.TEACHER, User.MemberType.VOLUNTEER, 'Tình nguyện viên', ['TA']),
]

STUDENTS = ['Phạm Văn An', 'Đỗ Thị Bình', 'Hoàng Minh Châu', 'Vũ Đức Dũng', 'Ngô Thị Giang', 'Bùi Quang Huy',
            'Đặng Thu Hương', 'Phan Văn Khoa', 'Trịnh Thị Linh', 'Lý Hoàng Nam', 'Mai Thị Oanh', 'Tạ Văn Phúc',
            'Chu Thị Quỳnh', 'Dương Văn Sơn', 'Hà Thị Trang']


class Command(BaseCommand):
    help = 'Fill an empty database with demo subjects, accounts, students and classes.'

    def add_arguments(self, parser):
        parser.add_argument('--password', default='bluedragon123', help='Password for every demo account.')
        parser.add_argument('--if-empty', action='store_true',
                            help='Do nothing (instead of failing) when the database already has accounts.')

    @transaction.atomic
    def handle(self, *args, password, if_empty, **options):
        if User.objects.exists():
            if if_empty:
                self.stdout.write('Database already has data; demo data not added.')
                return
            raise CommandError('Database already has accounts; demo data is only added to an empty database.')
        rng = random.Random(42)
        today = timezone.localdate()

        subjects = {code: Subject.objects.create(name=name, code=code) for name, code in SUBJECTS}

        users = {}
        for username, full_name, role, member_type, job, codes in ACCOUNTS:
            user = User(username=username, full_name=full_name, role=role, member_type=member_type,
                        current_job=job, phone=f'09{rng.randint(10000000, 99999999)}',
                        dob=datetime.date(rng.randint(1975, 2000), rng.randint(1, 12), rng.randint(1, 28)))
            user.set_password(password)
            user.save()
            user.subjects.set([subjects[c] for c in codes])
            users[username] = user

        students = []
        for name in STUDENTS:
            s = Student.objects.create(
                full_name=name, dob=datetime.date(rng.randint(2008, 2016), rng.randint(1, 12), rng.randint(1, 28)),
                social_worker_name=rng.choice(['Nguyễn Hồng Nhung', 'Trần Quốc Bảo', 'Lê Thị Mai']),
                social_worker_phone=f'09{rng.randint(10000000, 99999999)}')
            s.subjects.set(rng.sample(list(subjects.values()), 2))
            students.append(s)

        def make_class(subject, grade, teachers, studs, **schedule):
            c = StudyClass.objects.create(subject=subjects[subject], grade=grade, **schedule)
            c.teachers.set(teachers)
            c.students.set(studs)
            c.save()
            c.sync_sessions(include_past=True)
            return c

        monday = today - datetime.timedelta(days=today.weekday())
        toan = make_class('TO', 6, [users['gv.lan']], students[0:8], room='101', frequency='weekly',
                          weekdays='0,2', start_date=monday - datetime.timedelta(weeks=3),
                          end_date=monday + datetime.timedelta(weeks=10),
                          start_time=datetime.time(17, 30), end_time=datetime.time(19, 0))
        make_class('TA', 8, [users['tnv.anna']], students[5:14], room='203', frequency='biweekly',
                   weekdays='5', start_date=monday - datetime.timedelta(weeks=4),
                   end_date=monday + datetime.timedelta(weeks=12),
                   start_time=datetime.time(9, 0), end_time=datetime.time(10, 30))
        custom_days = [today + datetime.timedelta(days=d) for d in (-6, 1, 4, 11, 18)]
        make_class('TH', 7, [users['gv.minh']], students[2:7], room='Lab 1', frequency='custom',
                   custom_dates=', '.join(d.isoformat() for d in custom_days),
                   start_date=custom_days[0], end_date=custom_days[-1],
                   start_time=datetime.time(14, 0), end_time=datetime.time(16, 0))
        make_class('NV', 9, [users['dieuphoi']], students[10:15], room='102', frequency='weekly',
                   weekdays='3', start_date=monday, end_date=monday + datetime.timedelta(weeks=8),
                   start_time=datetime.time(18, 0), end_time=datetime.time(19, 30))

        ClassMaterial.objects.create(study_class=toan, title='Sách giáo khoa Toán 6 (PDF)',
                                     url='https://example.com/toan6', added_by=users['gv.lan'])

        # Submit attendance for past maths sessions so the dashboard shows real data.
        for session in toan.sessions.filter(date__lt=today):
            for student in toan.students.all():
                Attendance.objects.create(
                    session=session, student=student,
                    status=rng.choice(['present'] * 6 + ['late', 'excused', 'absent']),
                    feedback=rng.choice(['', 'Tiến bộ tốt.', 'Cần luyện thêm phân số.', 'Rất tích cực.']))
            session.teacher_comment = 'Buổi học diễn ra tốt.'
            session.submitted_at = timezone.now()
            session.submitted_by = users['gv.lan']
            session.save()

        self.stdout.write(self.style.SUCCESS('Demo data created. Accounts (password: %s):' % password))
        for username, full_name, role, *_ in ACCOUNTS:
            self.stdout.write(f'  {username:<10} {full_name} ({role.label})')
