"""Тесты этапа 1: схема БД, seed-данные и доступность страниц каркаса."""

from django.test import TestCase
from django.urls import reverse

from catalog.models import Ad, Book, Category, User


class SchemaTests(TestCase):
    """Миграции создают 4 таблицы со всеми полями из ТЗ (п.6)."""

    def test_four_tables_with_expected_columns(self):
        from django.db import connection

        expected = {
            "users": {
                "username",
                "password",
                "full_name",
                "email",
                "grade",
                "role",
                "is_active",
                "created_at",
            },
            "categories": {"name", "description"},
            "books": {
                "title",
                "author",
                "category_id",
                "cover",
                "description",
                "condition",
                "owner_id",
                "is_available",
                "created_at",
            },
            "ads": {
                "book_id",
                "author_id",
                "title",
                "text",
                "status",
                "created_at",
            },
        }
        with connection.cursor() as cursor:
            for table, columns in expected.items():
                actual = {
                    row[1] for row in cursor.execute(f"PRAGMA table_info({table})")
                }
                self.assertTrue(
                    columns <= actual,
                    f"таблица {table}: не хватает полей {sorted(columns - actual)}",
                )


class PageSmokeTests(TestCase):
    """Страницы /, /catalog, /exchange отвечают 200 с общим layout."""

    def test_pages_return_200_and_share_layout(self):
        paths = [reverse("catalog:home"), "/catalog/", reverse("exchange:exchange")]
        for path in paths:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            content = response.content.decode()
            self.assertIn("site-header", content, path)  # шапка: логотип + меню
            self.assertIn("site-footer", content, path)  # футер: контакты школы
            for menu_item in ("Главная", "Каталог", "Обмен"):
                self.assertIn(menu_item, content, path)

    def test_catalog_lists_books(self):
        owner = User.objects.create(username="librarian", full_name="Библиотекарь",
                                    role=User.Role.ADMIN)
        category = Category.objects.create(name="Учебники")
        Book.objects.create(title="Алгебра. 9 класс", author="Макарычев Ю.Н.",
                            category=category, owner=owner)
        response = self.client.get("/catalog/")
        self.assertContains(response, "Алгебра. 9 класс")

    def test_exchange_is_placeholder(self):
        response = self.client.get(reverse("exchange:exchange"))
        self.assertContains(response, "следующих этапах")


class SeedDataTests(TestCase):
    """Seed заполняет БД данными из DATA.md и идемпотентен."""

    def setUp(self):
        from io import StringIO

        from django.core.management import call_command

        call_command("seed_demo", stdout=StringIO())

    def _run_seed_again(self):
        from io import StringIO

        from django.core.management import call_command

        call_command("seed_demo", stdout=StringIO())

    def test_counts_match_data_md(self):
        self.assertEqual(User.objects.count(), 3)
        self.assertEqual(Category.objects.count(), 6)
        self.assertEqual(Book.objects.count(), 12)
        self.assertEqual(Ad.objects.count(), 3)

    def test_logins_and_roles(self):
        for login in ("admin", "student1", "student2"):
            self.assertTrue(User.objects.filter(username=login).exists(), login)
        self.assertEqual(User.objects.filter(role=User.Role.ADMIN).count(), 1)
        self.assertEqual(User.objects.filter(role=User.Role.STUDENT).count(), 2)

    def test_every_book_has_cover_file(self):
        import os

        from django.conf import settings

        for book in Book.objects.all():
            self.assertTrue(book.cover, f"нет обложки у «{book.title}»")
            self.assertTrue(
                os.path.isfile(os.path.join(settings.MEDIA_ROOT, book.cover.name)),
                f"файл обложки не найден: {book.cover.name}",
            )

    def test_seed_is_idempotent(self):
        self._run_seed_again()
        self.assertEqual(User.objects.count(), 3)
        self.assertEqual(Category.objects.count(), 6)
        self.assertEqual(Book.objects.count(), 12)
        self.assertEqual(Ad.objects.count(), 3)
        names = [b.cover.name for b in Book.objects.all()]
        self.assertEqual(len(names), len(set(names)), "обложки задублировались")
