from django.conf import settings


def nav(request):
    """The current top-level section ('class', 'teacher', ...) for highlighting the active tab."""
    match = request.resolver_match
    return {'nav_section': match.url_name.split('_')[0] if match and match.url_name else ''}


def demo(request):
    return {'demo_mode': settings.DEMO_MODE}
