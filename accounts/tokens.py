"""Генератор токена подтверждения e-mail.

Токен не зависит от пароля (подтверждение приходит до смены пароля),
но привязан к pk пользователя и состоянию email_confirmed — повторное
использование ссылки после подтверждения делает токен недействительным.
"""

from django.utils.crypto import constant_time_compare, salted_hmac


class EmailConfirmTokenGenerator:
    def make_token(self, user):
        return self._make_hash_value(user)

    def check_token(self, user, token):
        return constant_time_compare(token, self._make_hash_value(user))

    def _make_hash_value(self, user):
        return salted_hmac(
            "accounts.confirm_email",
            f"{user.pk}:{user.email}:{user.email_confirmed}",
        ).hexdigest()


account_token_generator = EmailConfirmTokenGenerator()
