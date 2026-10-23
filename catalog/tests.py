"""Тесты этапа 3: публичный каталог, фильтры, поиск, карточка книги."""

from django.test import TestCase
from django.urls import reverse

from catalog.models import Book, Category, User


class CatalogViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="u1", full_name="Тест Тест", email="u1@school.ru",
            password="pass12345", email_confirmed=True,
        )
        cls.textbooks = Category.objects.create(name="Учебники")
        cls.classics = Category.objects.create(name="Классика")
        cls.empty_cat = Category.objects.create(name="Пустая категория")
        Book.objects.create(title="Словарь маршей", author="Обобщённый автор",
                            category=cls.textbooks, owner=cls.user, year=2020)
        Book.objects.create(title="Стихотворения", author="Высоцкий В.С.",
                            category=cls.classics, owner=cls.user, year=2019)
        Book.objects.create(title="Марш энтузиастов", author="Дунаевский И.",
                            category=cls.classics, owner=cls.user, year=1980)

    def test_catalog_200_and_grid(self):
        r = self.client.get(reverse("catalog:catalog"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Словарь маршей", count=1)  # ровно одна карточка
        self.assertContains(r, "Найдено книг: 3")

    def test_search_marsh_finds_by_title_and_author_partial_case_insensitive(self):
        # «марш» находит по названию (в т.ч. внутри слова «маршей»), регистронезависимо
        r = self.client.get(reverse("catalog:catalog"), {"q": "МАРШ"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Словарь маршей")
        self.assertContains(r, "Марш энтузиастов")
        self.assertNotContains(r, "Стихотворения")
        self.assertContains(r, "Найдено книг: 2")

    def test_search_vysotz_finds_author(self):
        r = self.client.get(reverse("catalog:catalog"), {"q": "высоц"})
        self.assertContains(r, "Стихотворения")
        self.assertNotContains(r, "Словарь маршей")
        self.assertContains(r, "Найдено книг: 1")

    def test_empty_result_shows_message(self):
        r = self.client.get(reverse("catalog:catalog"), {"q": "жаба-хомяк"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Ничего не найдено")
        self.assertContains(r, "Найдено книг: 0")

    def test_category_page_only_its_books_with_counter(self):
        url = reverse("catalog:category", args=[self.classics.pk])
        r = self.client.get(url)
        self.assertContains(r, "Стихотворения")
        self.assertContains(r, "Марш энтузиастов")
        self.assertNotContains(r, "Словарь маршей")
        self.assertContains(r, "Категория: Классика")
        self.assertContains(r, '<span class="count-badge">2</span>')

    def test_filter_counters_in_sidebar(self):
        r = self.client.get(reverse("catalog:catalog"))
        self.assertContains(r, "Учебники (1)")
        self.assertContains(r, "Классика (2)")

    def test_filter_and_search_combine(self):
        r = self.client.get(reverse("catalog:catalog"), {
            "categories": [self.classics.pk], "q": "марш",
        })
        self.assertContains(r, "Марш энтузиастов")
        self.assertNotContains(r, "Словарь маршей")  # из другой категории отфильтровано
        self.assertContains(r, "Найдено книг: 1")

    def test_pagination_24_per_page(self):
        for i in range(30):
            Book.objects.create(title=f"Книга номер {i}", author="Разный",
                                category=self.textbooks, owner=self.user)
        r = self.client.get(reverse("catalog:catalog"))
        self.assertEqual(r.context["page_obj"].paginator.per_page, 24)
        self.assertEqual(len(r.context["page_obj"]), 24)
        self.assertTrue(r.context["page_obj"].has_next)
        r2 = self.client.get(reverse("catalog:catalog"), {"page": 2})
        self.assertEqual(len(r2.context["page_obj"]), 9)
        # ссылка на 2-ю страницу присутствует
        self.assertContains(r, "page=2")

    def test_book_detail_fields_and_catalog_number(self):
        book = Book.objects.get(title="Словарь маршей")
        r = self.client.get(reverse("catalog:book_detail", args=[book.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Каталожный номер")
        self.assertContains(r, book.catalog_number)
        self.assertContains(r, "2020")  # год
        self.assertContains(r, "Доступна для обмена")  # статус наличия

    def test_book_detail_no_cover_placeholder(self):
        book = Book.objects.create(title="Без обложки", author="Автор",
                                   category=self.textbooks, owner=self.user)
        r = self.client.get(reverse("catalog:book_detail", args=[book.pk]))
        self.assertContains(r, "Нет обложки")

    def test_book_detail_404(self):
        r = self.client.get("/book/99999/")
        self.assertEqual(r.status_code, 404)

    def test_catalog_number_autoassigned(self):
        book = Book.objects.first()
        self.assertTrue(book.catalog_number.startswith("ШК-"))

    def test_guest_can_view_catalog(self):
        for url in ["/catalog/", f"/catalog/{self.classics.pk}/",
                    f"/book/{Book.objects.first().pk}/"]:
            self.assertEqual(self.client.get(url).status_code, 200)
