"""Бэкенд аутентификации: вход по логину ИЛИ e-mail + пароль (по хешу).

Дополнительно: заблокированный пользователь (is_blocked=True) не может войти.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend


class EmailOrUsernameModelBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        if not username or not password:
            return None
        lookup = {"username": username}
        if "@" in username:
            lookup = {"email": username}
        try:
            user = User.objects.get(**lookup)
        except User.DoesNotExist:
            # Выполняем хеширование «вхолостую», чтобы время ответа
            # не отличалось от случая существующего пользователя.
            User().set_password(password)
            return None
        if user.check_password(password) and user.is_active and not user.is_blocked:
            return user
        return None

    def get_user(self, user_id):
        User = get_user_model()
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
