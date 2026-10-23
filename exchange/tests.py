"""Тесты этапа 4: доска объявлений и личный кабинет ученика."""

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from catalog.models import Ad, Book, Category, User

try:
    from PIL import Image

    def make_png(name="photo.png"):
        buf = BytesIO()
        Image.new("RGB", (10, 10), "red").save(buf, format="PNG")
        return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")
except ImportError:  # pragma: no cover
    def make_png(name="photo.png"):
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00"
            b"\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx"
            b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x00\x18\xdd\x8d\xb4\x00\x00"
            b"\x00\x00IEND\xaeB`\x82"
        )
        return SimpleUploadedFile(name, png_bytes, content_type="image/png")


class ExchangeBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="admin", password="pw-admin", full_name="Админ",
            email="admin@school.ru", role="admin",
        )
        cls.student1 = User.objects.create_user(
            username="student1", password="pw-student", full_name="Иван Петров",
            email="s1@school.ru", grade=9, role="student",
        )
        cls.student2 = User.objects.create_user(
            username="student2", password="pw-student", full_name="Мария Сидорова",
            email="s2@school.ru", grade=8, role="student",
        )
        cls.cat = Category.objects.create(name="Учебники")
        cls.book = Book.objects.create(
            title="Алгебра 9", author="Мерзляк", category=cls.cat,
            condition="good", owner=cls.admin,
        )

    def ad(self, author=None, **kwargs):
        data = {
            "title": "Отдам в добрые руки",
            "ad_type": Ad.Type.GIVE,
            "text": "Книга в хорошем состоянии",
            "contact": "s1@school.ru",
            "status": Ad.Status.ACTIVE,
            "book": self.book,
        }
        data.update(kwargs)
        return Ad.objects.create(author=author or self.student1, **data)


class ExchangeListTests(ExchangeBase):
    def test_guest_sees_active_feed_no_create_button(self):
        ad = self.ad()
        resp = self.client.get(reverse("exchange:list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, ad.title)
        self.assertNotContains(resp, "Создать объявление")

    def test_only_active_and_unblocked(self):
        archived = self.ad(title="В архиве", status=Ad.Status.ARCHIVED)
        closed = self.ad(title="Закрыто", status=Ad.Status.CLOSED)
        blocked_author = User.objects.create_user(
            username="blocked", password="pw", email="b@school.ru",
            role="student", is_blocked=True,
        )
        hidden = self.ad(author=blocked_author, title="От блокированного")
        visible = self.ad(title="Обычное")
        resp = self.client.get(reverse("exchange:list"))
        content = resp.content.decode()
        self.assertIn(visible.title, content)
        for t in (archived.title, closed.title, hidden.title):
            self.assertNotIn(t, content)

    def test_type_filters(self):
        give = self.ad(title="Отдам учебник", ad_type=Ad.Type.GIVE)
        seek = self.ad(title="Ищу роман", ad_type=Ad.Type.SEEK, author=self.student2)
        exch = self.ad(title="Обменяю сборник", ad_type=Ad.Type.EXCHANGE, author=self.student2)
        resp = self.client.get(reverse("exchange:list"), {"type": "seek"})
        content = resp.content.decode()
        self.assertIn(seek.title, content)
        self.assertNotIn(give.title, content)
        self.assertNotIn(exch.title, content)

    def test_search_by_title_case_insensitive(self):
        self.ad(title="Ищу Маршака раннего")
        self.ad(title="Отдам Высоцкого")
        resp = self.client.get(reverse("exchange:list"), {"q": "МАРШАК"})
        content = resp.content.decode()
        self.assertIn("Маршака", content)
        self.assertNotIn("Высоцкого", content)
        self.assertContains(resp, "Объявлений: 1")

    def test_empty_state(self):
        resp = self.client.get(reverse("exchange:list"), {"q": "йцукенневозможно"})
        self.assertContains(resp, "Ничего не найдено")

    def test_counters_match_counts(self):
        self.ad(ad_type=Ad.Type.GIVE)
        self.ad(title="второе", ad_type=Ad.Type.GIVE, author=self.student2)
        self.ad(title="третье", ad_type=Ad.Type.SEEK, author=self.student2)
        resp = self.client.get(reverse("exchange:list"))
        counts = resp.context["counts"]
        self.assertEqual(counts[Ad.Type.GIVE], 2)
        self.assertEqual(counts[Ad.Type.SEEK], 1)


class AdDetailTests(ExchangeBase):
    def test_detail_shows_all_fields(self):
        ad = self.ad()
        resp = self.client.get(reverse("exchange:detail", args=[ad.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, ad.title)
        self.assertContains(resp, ad.text)
        self.assertContains(resp, ad.contact)
        self.assertContains(resp, "Отдам")
        self.assertContains(resp, "Иван Петров")

    def test_archived_hidden_from_others_visible_to_owner(self):
        ad = self.ad(status=Ad.Status.ARCHIVED)
        resp = self.client.get(reverse("exchange:detail", args=[ad.pk]))
        self.assertEqual(resp.status_code, 302)
        self.client.force_login(self.student1)
        resp = self.client.get(reverse("exchange:detail", args=[ad.pk]))
        self.assertEqual(resp.status_code, 200)


class AdCrudTests(ExchangeBase):
    def test_student_creates_ad_appears_in_feed(self):
        self.client.force_login(self.student1)
        resp = self.client.post(reverse("exchange:create"), {
            "title": "Новое объявление",
            "book": self.book.pk,
            "ad_type": "give",
            "text": "Текст",
            "contact": "",
        })
        self.assertEqual(resp.status_code, 302)
        ad = Ad.objects.get(title="Новое объявление")
        self.assertEqual(ad.author, self.student1)
        self.assertEqual(ad.status, Ad.Status.ACTIVE)
        self.assertEqual(ad.contact, "s1@school.ru")  # из профиля
        feed = self.client.get(reverse("exchange:list")).content.decode()
        self.assertIn("Новое объявление", feed)

    def test_create_requires_login(self):
        resp = self.client.get(reverse("exchange:create"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp["Location"])

    def test_edit_own_ok_foreign_403(self):
        foreign = self.ad(author=self.student2, title="Чужое")
        own = self.ad(title="Своё")
        self.client.force_login(self.student1)
        resp = self.client.get(reverse("exchange:edit", args=[foreign.pk]))
        self.assertEqual(resp.status_code, 403)
        resp = self.client.get(reverse("exchange:edit", args=[own.pk]))
        self.assertEqual(resp.status_code, 200)
        resp = self.client.post(reverse("exchange:edit", args=[own.pk]), {
            "title": "Своё edited", "book": self.book.pk, "ad_type": "seek",
            "text": "Текст", "contact": "s1@school.ru",
        })
        self.assertEqual(resp.status_code, 302)
        own.refresh_from_db()
        self.assertEqual(own.title, "Своё edited")

    def test_delete_own_ok_foreign_403(self):
        foreign = self.ad(author=self.student2, title="Чужое")
        own = self.ad(title="Своё")
        self.client.force_login(self.student1)
        resp = self.client.post(reverse("exchange:delete", args=[foreign.pk]))
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Ad.objects.filter(pk=foreign.pk).exists())
        resp = self.client.post(reverse("exchange:delete", args=[own.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Ad.objects.filter(pk=own.pk).exists())

    def test_archive_removes_from_feed_keeps_in_my(self):
        ad = self.ad(title="Архивируемое")
        self.client.force_login(self.student1)
        resp = self.client.post(reverse("exchange:archive", args=[ad.pk]))
        self.assertEqual(resp.status_code, 302)
        ad.refresh_from_db()
        self.assertEqual(ad.status, Ad.Status.ARCHIVED)
        feed = self.client.get(reverse("exchange:list")).content.decode()
        self.assertNotIn("Архивируемое", feed)
        my = self.client.get(reverse("accounts:my")).content.decode()
        self.assertIn("Архивируемое", my)
        self.assertIn("В архиве", my)
        # возврат
        self.client.post(reverse("exchange:archive", args=[ad.pk]))
        ad.refresh_from_db()
        self.assertEqual(ad.status, Ad.Status.ACTIVE)

    def test_photo_upload_and_validation(self):
        self.client.force_login(self.student1)
        resp = self.client.post(reverse("exchange:create"), {
            "title": "С фото", "book": self.book.pk, "ad_type": "give",
            "text": "Т", "contact": "s1@school.ru", "photo1": make_png("p1.png"),
        })
        self.assertEqual(resp.status_code, 302)
        ad = Ad.objects.get(title="С фото")
        self.assertEqual(len(ad.photos), 1)
        page = self.client.get(reverse("exchange:detail", args=[ad.pk]))
        self.assertContains(page, ad.photos[0])

    def test_bad_photo_type_rejected(self):
        self.client.force_login(self.student1)
        bad = SimpleUploadedFile("doc.txt", b"not an image", content_type="text/plain")
        resp = self.client.post(reverse("exchange:create"), {
            "title": "Плохое фото", "book": self.book.pk, "ad_type": "give",
            "text": "Т", "contact": "s1@school.ru", "photo1": bad,
        })
        self.assertEqual(resp.status_code, 200)  # форма с ошибкой
        self.assertFalse(Ad.objects.filter(title="Плохое фото").exists())
        self.assertContains(resp, "допустимы только изображения")

    def test_more_than_three_photos_rejected(self):
        self.client.force_login(self.student1)
        data = {
            "title": "Четыре фото", "book": self.book.pk, "ad_type": "give",
            "text": "Т", "contact": "s1@school.ru",
            "photo1": make_png("a.png"), "photo2": make_png("b.png"),
            "photo3": make_png("c.png"),
        }
        resp = self.client.post(reverse("exchange:create"), data)
        self.assertEqual(resp.status_code, 302)
        ad = Ad.objects.get(title="Четыре фото")
        self.assertEqual(len(ad.photos), 3)
        # попытка добавить 4-е при редактировании
        resp = self.client.post(reverse("exchange:edit", args=[ad.pk]), {
            "title": "Четыре фото", "book": self.book.pk, "ad_type": "give",
            "text": "Т", "contact": "s1@school.ru", "photo1": make_png("d.png"),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "не более 3 фотографий")
        ad.refresh_from_db()
        self.assertEqual(len(ad.photos), 3)

    def test_admin_can_edit_any_ad(self):
        ad = self.ad(author=self.student1, title="Ученическое")
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("exchange:edit", args=[ad.pk]))
        self.assertEqual(resp.status_code, 200)


class MyAdsTests(ExchangeBase):
    def test_my_lists_own_ads_with_statuses(self):
        self.ad(title="Активное")
        self.ad(title="Архивное", status=Ad.Status.ARCHIVED)
        other = self.ad(author=self.student2, title="Чужое")
        self.client.force_login(self.student1)
        resp = self.client.get(reverse("accounts:my"))
        content = resp.content.decode()
        self.assertIn("Активное", content)
        self.assertIn("Архивное", content)
        self.assertNotIn("Чужое", content)
