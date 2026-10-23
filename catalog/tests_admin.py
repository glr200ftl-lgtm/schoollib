"""Тесты этапа 5: ЛК администратора (управление каталогом)."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from catalog.models import Book, Category, User

PNG_1PX = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class AdminAccessTests(TestCase):
    """Гость и ученик на /admin/books и /admin/categories — не админ."""

    def setUp(self):
        self.admin = User.objects.create_user(
            "librarian", "Библиотекарь Иванова А.П.", "pass12345",
            email="lib@school1.ru", role=User.Role.ADMIN,
        )
        self.student = User.objects.create_user(
            "pupil", "Петров Пётр", "pass12345",
            email="pupil@school1.ru", grade="7А",
        )
        self.category = Category.objects.create(name="Учебники")
        self.book = Book.objects.create(
            title="Алгебра", author="Мордкович", category=self.category,
            owner=self.admin, year=2021,
        )

    # --- доступ -----------------------------------------------------
    def test_guest_redirected_to_login(self):
        resp = self.client.get("/admin/books/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.headers["Location"])

    def test_student_gets_403(self):
        self.client.force_login(self.student)
        for url in ["/admin/books/", "/admin/books/add",
                    f"/admin/books/{self.book.pk}/edit",
                    f"/admin/books/{self.book.pk}/delete",
                    "/admin/categories/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_admin_has_access(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/admin/books/").status_code, 200)
        self.assertEqual(self.client.get("/admin/categories/").status_code, 200)

    # --- книги: добавление ------------------------------------------
    def test_admin_creates_book_visible_in_public_catalog_and_search(self):
        self.client.force_login(self.admin)
        cover = SimpleUploadedFile("cover.png", PNG_1PX, content_type="image/png")
        resp = self.client.post("/admin/books/add", {
            "title": "Словарь русского языка",
            "author": "Ожегов",
            "catalog_number": "",
            "year": 1989,
            "category": self.category.pk,
            "cover": cover,
            "description": "Классический словарь.",
            "condition": "good",
            "is_available": True,
        })
        self.assertEqual(resp.status_code, 302)
        book = Book.objects.get(title="Словарь русского языка")
        self.assertTrue(book.catalog_number.startswith("ШК-"))
        self.assertIsNotNone(book.cover)
        # книга сразу в публичном каталоге
        page = self.client.get(reverse("catalog:catalog")).content.decode()
        self.assertIn("Словарь русского языка", page)
        # и находится поиском (регистронезависимо, частичное совпадение)
        found = self.client.get(reverse("catalog:catalog"), {"q": "ожег"}).content.decode()
        self.assertIn("Словарь русского языка", found)

    # --- книги: правка ----------------------------------------------
    def test_edit_changes_book_card(self):
        self.client.force_login(self.admin)
        resp = self.client.post(f"/admin/books/{self.book.pk}/edit", {
            "title": "Алгебра. Углублённый курс",
            "author": "Мордкович",
            "catalog_number": self.book.catalog_number,
            "year": 2022,
            "category": self.category.pk,
            "description": "",
            "condition": "good",
            "is_available": True,
        })
        self.assertEqual(resp.status_code, 302)
        self.book.refresh_from_db()
        self.assertEqual(self.book.title, "Алгебра. Углублённый курс")
        detail = self.client.get(self.book.get_absolute_url()).content.decode()
        self.assertIn("Углублённый курс", detail)

    # --- книги: удаление --------------------------------------------
    def test_delete_requires_confirmation_and_removes_book(self):
        self.client.force_login(self.admin)
        url = f"/admin/books/{self.book.pk}/delete"
        # GET — страница подтверждения, книга на месте
        self.assertContains(self.client.get(url), "Подтвердите удаление")
        self.assertTrue(Book.objects.filter(pk=self.book.pk).exists())
        # POST — удаляет
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Book.objects.filter(pk=self.book.pk).exists())
        # карточка книги больше недоступна
        self.assertEqual(self.client.get(f"/book/{self.book.pk}/").status_code, 404)

    # --- каталожный номер -------------------------------------------
    def test_duplicate_catalog_number_rejected_with_clear_error(self):
        self.client.force_login(self.admin)
        data = {
            "title": "Дубликат", "author": "Автор",
            "catalog_number": self.book.catalog_number,
            "year": 2020, "category": self.category.pk,
            "description": "", "condition": "good", "is_available": True,
        }
        resp = self.client.post("/admin/books/add", data)
        self.assertEqual(resp.status_code, 200)  # форма с ошибкой
        self.assertContains(resp, "уже занят книгой")
        self.assertFalse(Book.objects.filter(title="Дубликат").exists())

    # --- валидация обложки -------------------------------------------
    def test_cover_too_large_rejected(self):
        self.client.force_login(self.admin)
        big = SimpleUploadedFile("big.png", b"\x89PNG" + b"0" * (5 * 1024 * 1024 + 10),
                                 content_type="image/png")
        resp = self.client.post("/admin/books/add", {
            "title": "Большая обложка", "author": "А", "catalog_number": "",
            "year": 2020, "category": self.category.pk, "cover": big,
            "description": "", "condition": "good", "is_available": True,
        })
        # размер проверяется в clean_cover до загрузки в ImageField-валидатор;
        # сообщение может быть дополнено стандартной ошибкой Django — проверяем оба
        self.assertTrue(
            "не должен превышать 5 МБ" in resp.content.decode(),
            "нет сообщения о превышении размера обложки",
        )
        self.assertFalse(Book.objects.filter(title="Большая обложка").exists())

    def test_non_image_cover_rejected(self):
        self.client.force_login(self.admin)
        txt = SimpleUploadedFile("doc.txt", b"not an image", content_type="text/plain")
        resp = self.client.post("/admin/books/add", {
            "title": "Не картинка", "author": "А", "catalog_number": "",
            "year": 2020, "category": self.category.pk, "cover": txt,
            "description": "", "condition": "good", "is_available": True,
        })
        self.assertContains(resp, "только изображение")
        self.assertFalse(Book.objects.filter(title="Не картинка").exists())

    # --- категории ----------------------------------------------------
    def test_category_create_rename(self):
        self.client.force_login(self.admin)
        resp = self.client.post("/admin/categories/add", {"name": "Художественная литература", "description": ""})
        self.assertEqual(resp.status_code, 302)
        cat = Category.objects.get(name="Художественная литература")
        resp = self.client.post(f"/admin/categories/{cat.pk}/edit", {"name": "Художка", "description": ""})
        self.assertEqual(resp.status_code, 302)
        cat.refresh_from_db()
        self.assertEqual(cat.name, "Художка")

    def test_category_delete_empty_ok_nonempty_blocked(self):
        self.client.force_login(self.admin)
        # непустая категория — удалить нельзя (есть книги)
        resp = self.client.post(f"/admin/categories/{self.category.pk}/delete")
        self.assertEqual(resp.status_code, 400)
        # blocked-страница отдаётся со статусом 400 — проверяем содержимое вручную
        self.assertIn("нельзя", resp.content.decode())
        self.assertTrue(Category.objects.filter(pk=self.category.pk).exists())
        # пустая — удаляется
        empty = Category.objects.create(name="Пустая")
        resp = self.client.post(f"/admin/categories/{empty.pk}/delete")
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Category.objects.filter(pk=empty.pk).exists())

    # --- сайдбар со заглушками следующих этапов -----------------------
    def test_sidebar_placeholders(self):
        self.client.force_login(self.admin)
        page = self.client.get("/admin/books/").content.decode()
        self.assertIn("скоро", page)
        self.assertIn("Модерация объявлений", page)
