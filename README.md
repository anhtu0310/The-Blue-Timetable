# Blue Time Table

Web dashboard for Blue Dragon's Learning & Development department: classes, schedules,
teachers/volunteers, students, attendance and session feedback. UI language: Vietnamese.

Stack: Django 5.2 + SQLite + HTMX + FullCalendar, with a custom stylesheet (`core/static/core/app.css`),
the Inter font and Lucide icons. All front-end libraries are vendored in
`core/static/vendor/`, so it runs offline with no Node/npm build step.

## Live demo

Hosted on Render's free plan (see "Deploy to Render" below). Log in with one of the demo
accounts, password `bluedragon123`. The free service sleeps when idle, so the first page can
take up to a minute to load. Demo data is reset every time the service restarts.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo          # optional: demo data, password "bluedragon123"
.venv/bin/python manage.py runserver
```

Open http://127.0.0.1:8000.

Demo accounts: `admin` (Quản trị viên), `dieuphoi` (Điều phối viên), `gv.lan`, `gv.minh`, `tnv.anna` (Giáo viên).

To start with real data instead, skip `seed_demo` and create the first admin with
`.venv/bin/python manage.py createsuperuser` (superusers automatically get the admin role).

Run the tests: `.venv/bin/python manage.py test core`

## Roles

| | Teacher | Moderator | Admin |
|---|---|---|---|
| Own profile, own classes and schedule, students in own classes | ✓ | ✓ | ✓ |
| Attendance + feedback for own sessions | ✓ | ✓ (any session) | ✓ (any session) |
| Create/edit classes, assign teachers/students, reschedule a single session | | ✓ | ✓ |
| Manage subjects (tags), view all teachers and students | | ✓ | ✓ |
| Create/edit/delete accounts and students, assign roles, unlock a submitted session, delete classes | | | ✓ |

## Rules implemented

- **Class code**: 2-letter subject code + 2-digit grade + 2-digit counter (00–99), e.g. `TO0601`. Generated automatically.
- **Max 10 students** per class.
- **Frequency**: weekly, every two weeks, or hand-picked dates. Sessions are generated from the schedule.
  Editing a class updates only future sessions that are not submitted and not individually rescheduled.
  Pausing/ending a class removes its future sessions; resuming recreates them.
- **Submit lock**: once attendance is submitted for a session, nobody can change it. Only an admin can unlock it.
  Attendance can be taken from the day of the session onward.
- **Session change** (moderators): change date/time/room/substitute teacher or cancel, for that one session only.
- **Change history** for classes and sessions (who changed what, when).
- **Search** teachers/students by name or subject tag: partial and accent-insensitive (`toan` finds `Toán`).

## Code map

- `core/models.py` – data model, class-code and session-generation logic
- `core/permissions.py` – who can see/do what
- `core/views.py`, `core/urls.py` – pages (Vietnamese URLs)
- `core/templates/core/` – HTML templates; `core/static/core/` – CSS and JS
- `core/management/commands/seed_demo.py` – demo data
- `/django-admin/` – Django's built-in admin, a low-level fallback for superusers

## Deploy to Render (public demo)

`render.yaml` describes the whole service. On https://render.com: sign in with GitHub,
choose **New → Blueprint**, pick this repository and click **Apply**. Render installs the
requirements, collects static files, then on every start runs migrations, loads the demo data
into the (empty) database and starts gunicorn. Every push to the repository redeploys it.

## Settings (environment variables)

| Variable | Meaning |
|---|---|
| `BTT_DEBUG` | `1` (default) for development; `0` in production (HTTPS-only cookies, compressed static files). |
| `BTT_SECRET_KEY` | Required when `BTT_DEBUG=0`. Long random string; Render generates one. |
| `BTT_ALLOWED_HOSTS` | Comma separated host names (default `localhost,127.0.0.1`). Render's host is added automatically. |
| `BTT_CSRF_TRUSTED_ORIGINS` | Extra origins allowed to submit forms, e.g. `https://lich.example.org` for a custom domain. |
| `BTT_DEMO` | `1` shows the demo accounts on the login page and disables password changes. |

Failed logins are limited to 5 per username and address, then locked for 15 minutes.

## Before using it with real data

The demo setup is not suitable for real student records. Use a host with a persistent disk
or a managed database and regular backups, keep `BTT_DEMO` unset, create accounts with
strong passwords, and serve it only over HTTPS.
