"""Тесты этапа 2: аутентификация и роли."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class RegisterTests(TestCase):
    def test_register_creates_hashed_password_and_confirm_email(self):
        resp = self.client.post(
            reverse("accounts:register"),
            {
                "full_name": "Тестовый Тест Тестович",
                "email": "new@school1.ru",
                "grade": "9А",
                "password1": "Sup3r-Secret!",
                "password2": "Sup3r-Secret!",
            },
        )
        self.assertRedirects(resp, reverse("accounts:login"))
        user = User.objects.get(email="new@school1.ru")
        # пароль хранится хешем
        self.assertTrue(user.password.startswith("pbkdf2_sha256$"))
        self.assertNotIn("Sup3r-Secret!", user.password)
        self.assertFalse(user.email_confirmed)
        self.assertEqual(user.role, User.Role.STUDENT)

    def test_duplicate_email_rejected(self):
        User.objects.create_user(
            username="dup@school1.ru",
            full_name="Дубликат Д.Д.",
            email="dup@school1.ru",
            password="SomePass123!",
            email_confirmed=True,
        )
        resp = self.client.post(
            reverse("accounts:register"),
            {
                "full_name": "Другой Друг Другович",
                "email": "DUP@school1.ru",
                "grade": "8Б",
                "password1": "Another-Pass1!",
                "password2": "Another-Pass1!",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "уже зарегистрирован")
        self.assertEqual(User.objects.filter(email__iexact="dup@school1.ru").count(), 1)

    def test_password_mismatch_rejected(self):
        resp = self.client.post(
            reverse("accounts:register"),
            {
                "full_name": "Разный Р.Р.",
                "email": "mismatch@school1.ru",
                "grade": "9В",
                "password1": "Password-One1!",
                "password2": "Password-Two2!",
            },
        )
        self.assertContains(resp, "Пароли не совпадают")
        self.assertFalse(User.objects.filter(email="mismatch@school1.ru").exists())


class LoginLogoutTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="student1",
            full_name="Петров Сергей Андреевич",
            email="petrov@school1.ru",
            grade="9А",
            password="student123",
            email_confirmed=True,
        )

    def test_login_by_username(self):
        resp = self.client.post(
            reverse("accounts:login"),
            {"username": "student1", "password": "student123"},
        )
        self.assertRedirects(resp, reverse("accounts:profile"))
        self.assertEqual(resp.wsgi_request.user.pk, self.student.pk)

    def test_login_by_email(self):
        resp = self.client.post(
            reverse("accounts:login"),
            {"username": "petrov@school1.ru", "password": "student123"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(getattr(resp.wsgi_request, "user", None) and resp.wsgi_request.user.is_authenticated)

    def test_wrong_password(self):
        resp = self.client.post(
            reverse("accounts:login"),
            {"username": "student1", "password": "wrongpass"},
        )
        self.assertContains(resp, "Неверный логин")

    def test_blocked_user_cannot_login(self):
        self.student.is_blocked = True
        self.student.save(update_fields=["is_blocked"])
        resp = self.client.post(
            reverse("accounts:login"),
            {"username": "student1", "password": "student123"},
        )
        self.assertContains(resp, "заблокирована")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unconfirmed_email_cannot_login(self):
        self.student.email_confirmed = False
        self.student.save(update_fields=["email_confirmed"])
        resp = self.client.post(
            reverse("accounts:login"),
            {"username": "student1", "password": "student123"},
        )
        self.assertContains(resp, "не подтверждён")

    def test_logout(self):
        self.client.login(username="student1", password="student123")
        resp = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(resp, reverse("catalog:home"))
        self.assertFalse(getattr(resp.wsgi_request, "user").is_authenticated)


class EmailConfirmTests(TestCase):
    def test_confirm_link_sets_flag(self):
        from accounts.tokens import account_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        user = User.objects.create_user(
            username="conf@school1.ru",
            full_name="Подтверждающий П.П.",
            email="conf@school1.ru",
            password="Pass-word123!",
        )
        token = account_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        resp = self.client.get(reverse("accounts:confirm_email", args=[uid, token]))
        self.assertContains(resp, "E-mail подтверждён")
        user.refresh_from_db()
        self.assertTrue(user.email_confirmed)

    def test_invalid_token(self):
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        user = User.objects.create_user(
            username="bad@school1.ru",
            full_name="Бад Б.Б.",
            email="bad@school1.ru",
            password="Pass-word123!",
        )
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        resp = self.client.get(
            reverse("accounts:confirm_email", args=[uid, "deadbeef"])
        )
        self.assertContains(resp, "недействительна")


class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="forgot@school1.ru",
            full_name="Забывший З.З.",
            email="forgot@school1.ru",
            password="Old-Pass123!",
            email_confirmed=True,
        )

    def test_reset_flow(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        resp = self.client.post(
            reverse("accounts:password_reset"), {"email": "forgot@school1.ru"}
        )
        self.assertContains(resp, "письмо со ссылкой отправлено")
        token = default_token_generator.make_token(self.user)
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        resp = self.client.post(
            reverse("accounts:password_reset_confirm", args=[uid, token]),
            {"new_password1": "New-Pass456!", "new_password2": "New-Pass456!"},
        )
        self.assertRedirects(resp, reverse("accounts:login"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("New-Pass456!"))

    def test_reset_unknown_email(self):
        resp = self.client.post(
            reverse("accounts:password_reset"), {"email": "ghost@nowhere.xx"}
        )
        self.assertContains(resp, "не найден")


class AccessControlTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="stud", full_name="Студент С.С.", email="stud@school1.ru",
            password="stud-pass123", role=User.Role.STUDENT, email_confirmed=True,
        )
        self.admin = User.objects.create_user(
            username="boss", full_name="Админ А.А.", email="boss@school1.ru",
            password="boss-pass123", role=User.Role.ADMIN, email_confirmed=True,
        )

    def test_guest_my_redirects_to_login(self):
        resp = self.client.get("/my/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:login"), resp["Location"])

    def test_student_admin_forbidden(self):
        self.client.login(username="stud", password="stud-pass123")
        resp = self.client.get("/admin/")
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_open_admin(self):
        self.client.login(username="boss", password="boss-pass123")
        resp = self.client.get("/admin/", follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Добро пожаловать")

    def test_public_pages_still_ok(self):
        for url in ["/", "/catalog/", "/exchange/"]:
            self.assertEqual(self.client.get(url).status_code, 200)


class ProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="prof@school1.ru", full_name="Профиль П.П.",
            email="prof@school1.ru", grade="9А",
            password="prof-pass123", email_confirmed=True,
        )
        self.client.login(username="prof@school1.ru", password="prof-pass123")

    def test_profile_update(self):
        resp = self.client.post(
            reverse("accounts:profile"),
            {
                "profile_submit": "1",
                "p-full_name": "Профиль П.П. Обновлённый",
                "p-grade": "10А",
                "p-email": "prof@school1.ru",
            },
        )
        self.assertRedirects(resp, reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.grade, "10А")
        self.assertIn("Обновлённый", self.user.full_name)

    def test_password_change(self):
        resp = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": "prof-pass123",
                "new_password1": "Fresh-Pass789!",
                "new_password2": "Fresh-Pass789!",
            },
        )
        self.assertRedirects(resp, reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Fresh-Pass789!"))
        # старая сессия остаётся валидной, новый пароль работает
        resp = self.client.get(reverse("accounts:my"))
        self.assertEqual(resp.status_code, 200)
