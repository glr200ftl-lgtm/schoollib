"""Seed-команда: заполнение БД демо-данными (Этап 1).

Запуск: python manage.py seed_demo

Создаёт:
- 1 администратор, 2 ученика;
- 6 категорий;
- 12 книг с обложками-заглушками (генерируются Pillow в MEDIA_ROOT/covers/);
- 3 объявления об обмене.

Команда идемпотентна: повторный запуск не создаёт дубликаты.
"""

from io import BytesIO

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from catalog.models import Ad, Book, Category, User

CATEGORIES = [
    ("Учебники", "Учебная литература по школьным предметам"),
    ("Художественная литература", "Романы, повести, рассказы, поэзия"),
    ("Научно-популярное", "Книги о науке и технике доступным языком"),
    ("Детская литература", "Книги для младших классов"),
    ("Справочники и словари", "Энциклопедии, словари, атласы"),
    ("Подготовка к экзаменам", "ОГЭ, ЕГЭ, олимпиадные задания"),
]

USERS = [
    {
        "username": "admin",
        "full_name": "Иванова Мария Петровна",
        "email": "admin@school1.ru",
        "grade": "",
        "role": User.Role.ADMIN,
        "password": "admin123",
    },
    {
        "username": "student1",
        "full_name": "Петров Сергей Андреевич",
        "email": "petrov@school1.ru",
        "grade": "9А",
        "role": User.Role.STUDENT,
        "password": "student123",
    },
    {
        "username": "student2",
        "full_name": "Сидорова Анна Игоревна",
        "email": "sidorova@school1.ru",
        "grade": "8Б",
        "role": User.Role.STUDENT,
        "password": "student123",
    },
]

# (название, автор, категория, состояние)
BOOKS = [
    ("Алгебра. 9 класс", "Макарычев Ю.Н.", "Учебники", "good"),
    ("Физика. 8 класс", "Пёрышкин А.В.", "Учебники", "fair"),
    ("Война и мир. Том 1", "Толстой Л.Н.", "Художественная литература", "good"),
    ("Мастер и Маргарита", "Булгаков М.А.", "Художественная литература", "new"),
    ("Краткая история времени", "Хокинг С.", "Научно-популярное", "good"),
    ("Занимательная химия", "Левашов М.", "Научно-популярное", "fair"),
    ("Маленький принц", "Де Сент-Экзюпери А.", "Детская литература", "new"),
    ("Приключения Незнайки", "Носов Н.Н.", "Детская литература", "good"),
    ("Большой энциклопедический словарь", "Ред. Прохоров А.M.", "Справочники и словари", "fair"),
    ("Атлас по географии. 7 класс", "Дронов В.П.", "Справочники и словари", "good"),
    ("ЕГЭ. Математика. Типовые варианты", "Ященко И.В.", "Подготовка к экзаменам", "new"),
    ("ОГЭ. Русский язык. Сочинение", "Цыбулько И.П.", "Подготовка к экзаменам", "good"),
]

ADS = [
    (
        "Обменяю «Алгебра. 9 класс» на учебник геометрии",
        "Книга в хорошем состоянии, без помарок. Ищу учебник geometry 9 класс Мерзляк или аналог. Могу добавить книгу по физике.",
        "Алгебра. 9 класс",
        "student1",
    ),
    (
        "«Маленький принц» — новый, отдам за «Войну и мир»",
        "Совершенно новая книга, читала один раз. Интересен обмен на Толстого в любом состоянии.",
        "Маленький принц",
        "student2",
    ),
    (
        "Срочно! Учебник физики 8 класс для обмена",
        "Отдам «Занимательную химию» + справочник по математике за учебник Пёрышкина. Договориться можно после уроков в библиотеке.",
        "Физика. 8 класс",
        "student1",
    ),
]


def make_cover_image(title: str, author: str):
    """Генерирует PNG-обложку-заглушку: цветной фон + текст названия.

    Цвет подбирается детерминированно (md5 от названия), а не через built-in
    hash(): он зависит от PYTHONHASHSEED и давал бы разные обложки при каждом
    новом запуске.
    """
    import hashlib

    from PIL import Image, ImageDraw

    width, height = 300, 420
    h = int(hashlib.md5(title.encode("utf-8")).hexdigest(), 16)
    color = (40 + h % 180, 60 + (h // 7) % 150, 90 + (h // 13) % 140)
    img = Image.new("RGB", (width, height), color)
    draw = ImageDraw.Draw(img)
    draw.rectangle([8, 8, width - 9, height - 9], outline=(255, 255, 255), width=3)

    # Перенос текста по словам (шрифт Pillow по умолчанию поддерживает только ASCII,
    # поэтому транслитерируем название и автора).
    TRANSLIT = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }

    def translit(text: str) -> str:
        return "".join(TRANSLIT.get(ch.lower(), ch) for ch in text)

    lines = []
    words = translit(f"{title} / {author}").split()
    line = ""
    for w in words:
        candidate = f"{line} {w}".strip()
        if len(candidate) <= 18:
            line = candidate
        else:
            lines.append(line)
            line = w
    if line:
        lines.append(line)

    y = 120
    for ln in lines[:10]:
        tw = draw.textlength(ln)
        draw.text(((width - tw) / 2, y), ln, fill=(255, 255, 255))
        y += 22

    buf = BytesIO()
    img.save(buf, format="PNG")
    return ContentFile(buf.getvalue())


class Command(BaseCommand):
    help = "Заполняет базу демо-данными: пользователи, категории, книги, объявления."

    def handle(self, *args, **options):
        # Пользователи
        user_map = {}
        for data in USERS:
            login = data["username"]
            user, created = User.objects.get_or_create(
                username=login,
                defaults={
                    "full_name": data["full_name"],
                    "email": data["email"],
                    "grade": data["grade"],
                    "role": data["role"],
                    "password": make_password(data["password"]),
                },
            )
            user_map[login] = user
            self.stdout.write(
                f"{'+' if created else '='} пользователь: {login}"
            )

        # Категории
        cat_map = {}
        for name, desc in CATEGORIES:
            cat, created = Category.objects.get_or_create(name=name, defaults={"description": desc})
            cat_map[name] = cat
            self.stdout.write(f"{'+' if created else '='} категория: {name}")

        # Книги с обложками-заглушками
        book_map = {}
        owners = [user_map["student1"], user_map["student2"]]
        for i, (title, author, cat_name, condition) in enumerate(BOOKS):
            owner = owners[i % 2]
            book, created = Book.objects.get_or_create(
                title=title,
                author=author,
                defaults={
                    "category": cat_map[cat_name],
                    "condition": condition,
                    "owner": owner,
                    "description": f"Демо-книга каталога школьной библиотеки: «{title}».",
                },
            )
            if not book.cover:
                # Детерминированное имя файла (md5 от названия), чтобы повторный
                # запуск не создавал дубликаты обложек. Django добавляет случайный
                # суффикс только если файл с таким именем уже существует; поэтому
                # сначала удаляем старый сгенерированный файл.
                import hashlib
                import os

                digest = hashlib.md5(title.encode("utf-8")).hexdigest()[:8]
                filename = f"{i + 1:02d}_{digest}.png"

                old_name = book.cover.name
                if old_name:
                    try:
                        old_path = book.cover.path
                    except (ValueError, NotImplementedError):
                        old_path = None
                    book.delete()  # отвязывает и удаляет старый файл обложки
                    expected_path = os.path.join(
                        str(settings.MEDIA_ROOT), "covers", filename
                    )
                    if (
                        old_path
                        and old_path != expected_path
                        and os.path.isfile(old_path)
                    ):
                        # чистим «осиротевший» файл со случайным суффиксом
                        os.remove(old_path)

                book.cover.save(filename, make_cover_image(title, author), save=True)
            book_map[title] = book
            self.stdout.write(f"{'+' if created else '='} книга: {title}")

        # Объявления
        ads_created = 0
        for title, text, book_title, author_login in ADS:
            _, created = Ad.objects.get_or_create(
                title=title,
                defaults={
                    "text": text,
                    "book": book_map[book_title],
                    "author": user_map[author_login],
                    "status": Ad.Status.ACTIVE,
                },
            )
            ads_created += created
            self.stdout.write(f"{'+' if created else '='} объявление: {title}")

        self.stdout.write(
            self.style.SUCCESS(
                "Seed завершён: %(u)d пользователей, %(c)d категорий, %(b)d книг, %(a)d объявлений."
                % {
                    "u": User.objects.count(),
                    "c": Category.objects.count(),
                    "b": Book.objects.count(),
                    "a": Ad.objects.count(),
                }
            )
        )
