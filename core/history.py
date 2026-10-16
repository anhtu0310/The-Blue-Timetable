"""Turns django-simple-history records into readable change lists."""
import datetime

from django.db import models

from .models import WEEKDAY_NAMES

HIDDEN_FIELDS = ['number', 'search_name', 'original_date']
# Edits saved within this window by the same person are shown as one entry
# (a class edit is saved twice so teacher/student lists get recorded).
MERGE_WINDOW = datetime.timedelta(seconds=5)


def _format(field, value):
    if value in (None, ''):
        return '—'
    if field.choices:
        return dict(field.flatchoices).get(value, value)
    if isinstance(field, models.ForeignKey):
        obj = field.related_model.objects.filter(pk=value).first()
        return str(obj) if obj else f'#{value}'
    if isinstance(field, models.BooleanField):
        return 'Có' if value else 'Không'
    if field.name == 'weekdays':
        return ', '.join(WEEKDAY_NAMES[int(d)] for d in value.split(',') if d.isdigit()) or '—'
    if isinstance(value, datetime.datetime):
        return f'{value:%d/%m/%Y %H:%M}'
    if isinstance(value, datetime.date):
        return f'{value:%d/%m/%Y}'
    if isinstance(value, datetime.time):
        return f'{value:%H:%M}'
    return str(value)


def _m2m_change(field, old, new):
    """Describe a teacher/student list change as who was added and removed."""
    key = field.related_model._meta.model_name
    old_ids = {row[key] for row in old}
    new_ids = {row[key] for row in new}
    names = {o.pk: str(o) for o in field.related_model.objects.filter(pk__in=old_ids | new_ids)}
    parts = []
    if new_ids - old_ids:
        parts.append('thêm ' + ', '.join(names.get(i, f'#{i}') for i in new_ids - old_ids))
    if old_ids - new_ids:
        parts.append('bớt ' + ', '.join(names.get(i, f'#{i}') for i in old_ids - new_ids))
    return '; '.join(parts)


def describe_history(obj):
    """Return [{'when', 'who', 'created', 'changes': [(label, old, new)]}], newest first.

    `old` is None for teacher/student list changes, where `new` describes the difference.
    """
    model = type(obj)
    records = list(obj.history.select_related('history_user').order_by('history_date'))
    entries = []
    prev = None
    for record in records:
        changes = []
        if prev is not None:
            delta = record.diff_against(prev, excluded_fields=HIDDEN_FIELDS)
            for change in delta.changes:
                field = model._meta.get_field(change.field)
                if field.many_to_many:
                    changes.append((field.verbose_name, None, _m2m_change(field, change.old, change.new)))
                else:
                    changes.append((field.verbose_name, _format(field, change.old), _format(field, change.new)))
        prev = record
        created = record.history_type == '+'
        if not created and not changes:
            continue
        last = entries[-1] if entries else None
        if (last and not created and last['who'] == record.history_user
                and record.history_date - last['when'] <= MERGE_WINDOW):
            last['changes'].extend(changes)
            continue
        entries.append({'when': record.history_date, 'who': record.history_user,
                        'created': created, 'changes': changes})
    return entries[::-1]
