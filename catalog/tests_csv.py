"""Тесты этапа 6: CSV-импорт и экспорт каталога."""

import csv
import io
import zipfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from catalog.models import Book, Category, User

HEADERS = ["Название", "Автор", "Каталожный номер", "Год", "Категория", "Описание", "URL обложки"]


def make_csv(rows, delimiter=";", bom=True):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delimiter, lineterminator="\r\n")
    w.writerow(HEADERS)
    for r in rows:
        w.writerow(r)
    text = buf.getvalue()
    return (("\ufeff" if bom else "") + text).encode("utf-8")


def png_bytes(color=(200, 30, 30)):
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (40, 60), color).save(b, "PNG")
    return b.getvalue()


class CsvImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            "boss", "Боссов И.И.", password="pw12345", role=User.Role.ADMIN, email_confirmed=True
        )
        cls.student = User.objects.create_user(
            "petrov", "Петров П.П.", password="pw12345", email="p@school.ru"
        )
        cls.cat = Category.objects.create(name="Алгебра")

    def setUp(self):
        self.client.force_login(self.admin)
        self.url = reverse("catalog_admin:import")

    # --- критерий: файл на 100 строк → 100 книг -------------------------
    def test_import_100_rows_creates_100_books_and_new_categories(self):
        rows = [
            [f"Учебник N{i}", f"Автор И.И. {i}", f"IMP-{i:04d}", 2021, f"Импортная категория {i % 3 + 1}", "", ""]
            for i in range(1, 101)
        ]
        resp = self.client.post(self.url, {
            "csv_file": SimpleUploadedFile("books.csv", make_csv(rows), content_type="text/csv"),
            "mode": "add", "apply": "yes", "confirm_mode": "add",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "добавлено <strong>100</strong>", html=False)
        self.assertEqual(Book.objects.filter(catalog_number__startswith="IMP-").count(), 100)
        # новые категории созданы автоматически
        self.assertTrue(Category.objects.filter(name="Импортная категория 1").exists())
        # книги видны в публичном каталоге и находятся поиском
        page = self.client.get("/catalog/?q=Учебник N77")
        self.assertContains(page, "Учебник N77")

    # --- dry-run: предпросмотр не изменяет данные ------------------------
    def test_preview_does_not_modify_database(self):
        rows = [["Тест Предпросмотр", "Тестер Т.Т.", "PREV-1", 2022, "Алгебра", "", ""]]
        before = Book.objects.count()
        resp = self.client.post(self.url, {
            "csv_file": SimpleUploadedFile("b.csv", make_csv(rows), content_type="text/csv"),
            "mode": "add",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Будет добавлено: <strong>1</strong>", html=False)
        self.assertEqual(Book.objects.count(), before, "предпросмотр не должен писать в базу")

    # --- upsert: ровно изменённые строки --------------------------------
    def test_upsert_updates_only_changed_rows(self):
        base = [[f"Книга {i}", f"Автор {i}", f"UP-{i:03d}", 2020, "Алгебра", "старое описание", ""] for i in range(1, 11)]
        self.client.post(self.url, {
            "csv_file": SimpleUploadedFile("b.csv", make_csv(base), content_type="text/csv"),
            "mode": "add", "apply": "yes", "confirm_mode": "add",
        })
        # меняем 5 строк (описание) + добавляем 2 новые
        changed = []
        for idx, row in enumerate(base):
            r = list(row)
            if idx < 5:
                r[5] = "НОВОЕ описание"
            changed.append(r)
        changed.append(["Добавленная A", "Автор А", "UP-101", 2023, "Алгебра", "", ""])
        changed.append(["Добавленная B", "Автор Б", "UP-102", 2023, "Геометрия", "", ""])
        resp = self.client.post(self.url, {
            "csv_file": SimpleUploadedFile("b.csv", make_csv(changed), content_type="text/csv"),
            "mode": "upsert", "apply": "yes", "confirm_mode": "upsert",
        })
        self.assertContains(resp, "добавлено <strong>2</strong>", html=False)
        self.assertContains(resp, "обновлено <strong>5</strong>", html=False)
        updated = Book.objects.filter(description="НОВОЕ описание").count()
        self.assertEqual(updated, 5)
        unchanged = Book.objects.filter(title="Книга 10", description="старое описание").count()
        self.assertEqual(unchanged, 1)

    def test_add_mode_skips_existing_numbers(self):
        rows = [["Существующая", "Автор С", "EX-1", 2020, "Алгебра", "", ""]]
        self.client.post(self.url, {
            "csv_file": SimpleUploadedFile("b.csv", make_csv(rows), content_type="text/csv"),
            "mode": "add", "apply": "yes", "confirm_mode": "add",
        })
        resp = self.client.post(self.url, {
            "csv_file": SimpleUploadedFile("b.csv", make_csv(rows), content_type="text/csv"),
            "mode": "add", "apply": "yes", "confirm_mode": "add",
        })
        self.assertContains(resp, "добавлено <strong>0</strong>", html=False)
        self.assertContains(resp, "уже существует", html=False)
        self.assertEqual(Book.objects.filter(catalog_number="EX-1").count(), 1)

    # --- битые строки: отчёт с номерами, остальные импортированы ---------
    def test_broken_rows_reported_by_number_rest_imported(self):
        Book.objects.create(title="Занятая", author="Владелец В", catalog_number="DUP-1",
                            category=self.cat, owner=self.admin)
        rows = [
            ["", "Автор А.", "R-001", 2020, "Алгебра", "", ""],              # строка 2: нет названия
            ["Дубль", "Автор Д", "DUP-1", 2020, "Алгебра", "", ""],          # строка 3: дубль номера в базе
            ["Мусор без автора", "", "R-003", 2020, "Алгебра", "", ""],      # строка 4: пустой автор
            ["Мусорный год", "Год Г.", "R-005", "не число", "Алгебра", "", ""],  # строка 5: некорректный год
            ["Хорошая книга", "Хороший А.А.", "R-004", 2021, "Алгебра", "", ""],
        ]
        data = make_csv(rows)
        resp = self.client.post(self.url, {
            "csv_file": SimpleUploadedFile("b.csv", data, content_type="text/csv"),
            "mode": "upsert", "apply": "yes", "confirm_mode": "upsert",
        })
        self.assertContains(resp, "ошибок <strong>3</strong>", html=False)
        self.assertContains(resp, "добавлено <strong>1</strong>", html=False)
        content = resp.content.decode()
        # битые строки (нет названия / пустой автор / мусорный год) — в отчёте
        # под своими номерами; корректных строк в этом файле 2:
        # «Дубль» DUP-1 обновляет существующую книгу (не ошибка),
        # «Хорошая книга» R-004 добавляется.
        for n in ("2", "4", "5"):
            self.assertIn(f"<td>{n}</td>", content, f"в отчёте нет строки {n}")
        self.assertNotIn("<td>3</td>", content)
        self.assertNotIn("<td>6</td>", content)
        # согласованный род: «пустое название», «пустой автор»
        self.assertIn("пустое название", content)
        self.assertIn("пустой автор", content)
        # дубль номера в базе не создаёт вторую запись
        self.assertEqual(Book.objects.filter(catalog_number="DUP-1").count(), 1)
        self.assertTrue(Book.objects.filter(catalog_number="R-004").exists())
        self.assertFalse(Book.objects.filter(catalog_number="R-003").exists())

    def test_duplicate_number_inside_file_is_error(self):
        rows = [
            ["Первая", "Автор А", "INFILE-1", 2020, "Алгебра", "", ""],
            ["Вторая-дубль", "Автор Б", "INFILE-1", 2020, "Алгебра", "", ""],
        ]
        resp = self.client.post(self.url, {
            "csv_file": SimpleUploadedFile("b.csv", make_csv(rows), content_type="text/csv"),
            "mode": "add", "apply": "yes", "confirm_mode": "add",
        })
        self.assertContains(resp, "добавлено <strong>1</strong>", html=False)
        self.assertContains(resp, "ошибок <strong>1</strong>", html=False)
        self.assertIn("дубль каталожного номера", resp.content.decode())

    # --- разделители и кодировки ------------------------------------------
    def test_comma_delimiter_and_no_bom(self):
        rows = [["Запятая", "Комма К.К.", "COM-1", 2020, "Алгебра", "", ""]]
        resp = self.client.post(self.url, {
            "csv_file": SimpleUploadedFile("b.csv", make_csv(rows, delimiter=",", bom=False), content_type="text/csv"),
            "mode": "add", "apply": "yes", "confirm_mode": "add",
        })
        self.assertContains(resp, "добавлено <strong>1</strong>", html=False)

    def test_bad_encoding_error_message(self):
        data = "Название;Автор\r\n".encode("cp1251") + "Щещщ".encode("cp1251")
        resp = self.client.post(self.url, {
            "csv_file": SimpleUploadedFile("b.csv", data, content_type="text/csv"),
            "mode": "add",
        })
        self.assertContains(resp, "UTF-8")

    # --- обложки из ZIP ----------------------------------------------------
    def test_cover_from_zip_archive(self):
        zbuf = io.BytesIO()
        with zipfile.ZipFile(zbuf, "w") as zf:
            zf.writestr("cover-a.png", png_bytes((10, 120, 10)))
        zip_bytes = zbuf.getvalue()
        rows = [["С обложкой", "Пиксель П.П.", "ZC-1", 2020, "Алгебра", "", "cover-a.png"]]
        resp = self.client.post(self.url, {
            "csv_file": SimpleUploadedFile("b.csv", make_csv(rows), content_type="text/csv"),
            "zip_file": SimpleUploadedFile("covers.zip", zip_bytes, content_type="application/zip"),
            "mode": "add", "apply": "yes", "confirm_mode": "add",
        })
        self.assertContains(resp, "добавлено <strong>1</strong>", html=False)
        book = Book.objects.get(catalog_number="ZC-1")
        self.assertTrue(book.cover, "обложка должна быть сохранена из ZIP")
        # и отображается в карточке
        page = self.client.get(f"/book/{book.pk}/")
        self.assertContains(page, book.cover.url)

    def test_missing_cover_in_zip_is_row_error(self):
        rows = [["Без файла", "Нет Н.Н.", "ZM-1", 2020, "Алгебра", "", "ghost.png"]]
        resp = self.client.post(self.url, {
            "csv_file": SimpleUploadedFile("b.csv", make_csv(rows), content_type="text/csv"),
            "mode": "add", "apply": "yes", "confirm_mode": "add",
        })
        self.assertContains(resp, "ошибок <strong>1</strong>", html=False)
        self.assertIn("не найдена", resp.content.decode())

    # --- доступ ------------------------------------------------------------
    def test_student_and_guest_cannot_import(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.logout()
        resp = self.client.get(self.url)
        self.assertIn(resp.status_code, (302, 403))


class CsvExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            "boss2", "Боссов И.И.", password="pw12345", role=User.Role.ADMIN, email_confirmed=True,
            email="boss2@school.ru",
        )
        cls.cat = Category.objects.create(name="Физика")
        cls.b1 = Book.objects.create(title="Механика", author="Ландау Л.Л.", catalog_number="EX-001",
                                     year=1978, category=cls.cat, owner=cls.admin, description="Курс")
        cls.b2 = Book.objects.create(title="Колебания", author="Мандельштам М.М.", catalog_number="EX-002",
                                     year=1933, category=cls.cat, owner=cls.admin)

    def setUp(self):
        self.client.force_login(self.admin)

    def _export(self, query=""):
        resp = self.client.get(reverse("catalog_admin:export") + query)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"].split(";")[0], "text/csv")
        raw = resp.content
        self.assertTrue(raw.startswith("\ufeff".encode("utf-8")), "экспорт должен начинаться с UTF-8 BOM")
        return raw.decode("utf-8-sig")

    def test_export_all_columns_match_import(self):
        text = self._export()
        rows = list(csv.reader(io.StringIO(text), delimiter=";"))
        self.assertEqual(rows[0], HEADERS, "колонки экспорта = колонкам импорта")
        self.assertEqual(len(rows), 3)  # заголовок + 2 книги

    def test_export_filtered(self):
        text = self._export("?q=колеб")
        rows = list(csv.reader(io.StringIO(text), delimiter=";"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], "Колебания")

    def test_roundtrip_edit_like_excel(self):
        """Экспорт → правка «в Excel» (меняем год и описание) → импорт upsert → данные не потеряны."""
        text = self._export()
        rows = list(csv.reader(io.StringIO(text), delimiter=";"))
        header, data = rows[0], rows[1:]
        for r in data:
            if r[0] == "Механика":
                r[3] = "2024"          # поправили год
                r[5] = "Обновлённый курс физики"
            elif r[0] == "Колебания":
                r[1] = "Мандельштам М. М."  # поправили написание автора
        edited = "\r\n".join([";".join(header)] + [";".join(r) for r in data])
        payload = ("\ufeff" + edited).encode("utf-8")
        imp = self.client.post(reverse("catalog_admin:import"), {
            "csv_file": SimpleUploadedFile("out.csv", payload, content_type="text/csv"),
            "mode": "upsert", "apply": "yes", "confirm_mode": "upsert",
        })
        self.assertContains(imp, "обновлено <strong>2</strong>", html=False)
        self.assertContains(imp, "добавлено <strong>0</strong>", html=False)
        self.assertContains(imp, "ошибок <strong>0</strong>", html=False)
        b1 = Book.objects.get(pk=self.b1.pk)
        self.assertEqual(b1.year, 2024)
        self.assertEqual(b1.description, "Обновлённый курс физики")
        self.assertEqual(Book.objects.count(), 2, "round-trip не плодит дублей")

    def test_export_requires_admin(self):
        self.client.logout()
        resp = self.client.get(reverse("catalog_admin:export"))
        self.assertIn(resp.status_code, (302, 403))
