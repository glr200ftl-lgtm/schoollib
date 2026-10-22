"""Декораторы и middleware проверки доступа по ролям (Этап 2).

Роли: guest (не аутентифицирован), student, admin.
- role_required(...) — аналог login_required с проверкой роли;
  гость редиректится на вход, чужая роль получает 403.
- AdminOnlyMiddleware — закрывает /admin/ для всех, кроме role=admin.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles, login_url=None):
    """Доступ только для указанных ролей.

    Гость -> редирект на страницу входа (с next);
    аутентифицированный без нужной роли -> 403 Forbidden.
    """

    def decorator(view_func):
        @wraps(view_func)
        @login_required(login_url=login_url)
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if not roles:
                return view_func(request, *args, **kwargs)
            if user.is_authenticated and user.role in roles:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied("Раздел доступен только для роли: " + ", ".join(roles))

        return _wrapped

    return decorator


def student_required(view_func=None, *, login_url=None):
    """Только ученики (админ — не ученик по роли ТЗ)."""
    from catalog.models import User

    if view_func is None:
        return role_required(User.Role.STUDENT, login_url=login_url)
    return role_required(User.Role.STUDENT, login_url=login_url)(view_func)


def admin_required(view_func=None, *, login_url=None):
    """Только администраторы (библиотекари)."""
    from catalog.models import User

    if view_func is None:
        return role_required(User.Role.ADMIN, login_url=login_url)
    return role_required(User.Role.ADMIN, login_url=login_url)(view_func)


class AdminOnlyMiddleware:
    """Гость на /admin/ -> редирект на вход; не-админ -> 403."""

    ADMIN_PREFIX = "/admin/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(self.ADMIN_PREFIX):
            user = getattr(request, "user", None)
            if user is None or not user.is_authenticated:
                from django.shortcuts import redirect
                from urllib.parse import quote

                return redirect(f"/login/?next={quote(request.full_path)}")
            if user.role != "admin":
                from django.core.exceptions import PermissionDenied

                raise PermissionDenied("Раздел администратора недоступен для этой роли.")
        return self.get_response(request)
