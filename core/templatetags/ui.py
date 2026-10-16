from django import template
from django.templatetags.static import static
from django.utils.html import format_html

register = template.Library()


@register.simple_tag(takes_context=True)
def form_attrs(context, url, confirm=''):
    """Form attributes that post via HTMX inside the pop-up, or normally on a full page."""
    if context['request'].htmx:
        return format_html('method="post" action="{0}" hx-post="{0}" hx-target="#modal-body"{1}', url,
                           format_html(' hx-confirm="{}"', confirm) if confirm else '')
    return format_html('method="post" action="{0}"{1}', url,
                       format_html(' onsubmit="return confirm(\'{}\')"', confirm) if confirm else '')


@register.simple_tag(takes_context=True)
def modal_link(context, url):
    """Link attributes that open `url` in the pop-up when already in one, else navigate."""
    if context['request'].htmx:
        return format_html('href="{0}" hx-get="{0}" hx-target="#modal-body"', url)
    return format_html('href="{0}"', url)


@register.simple_tag
def icon(name, extra_class=''):
    """Inline reference to an icon in the Lucide sprite (core/static/core/icons.svg)."""
    return format_html('<svg class="icon {}" aria-hidden="true"><use href="{}#i-{}"></use></svg>',
                       extra_class, static('core/icons.svg'), name)


@register.filter
def initials(person):
    """'Nguyễn Thị Lan' -> 'NL' (first and last word), for avatar circles."""
    words = str(person).split()
    if not words:
        return '?'
    return (words[0][0] + (words[-1][0] if len(words) > 1 else '')).upper()
