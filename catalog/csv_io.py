"""CSV-импорт и экспорт каталога книг (Этап 6).

Формат CSV (колонки = колонкам импорта, round-trip с экспортом):
    Название;Автор;Каталожный номер;Год;Категория;Описание;URL обложки

Разделитель ( ; или , ) и кодировка (UTF-8 / UTF-8 BOM) определяются
автоматически. Категории, отсутствующие в базе, создаются автоматически.

Режимы импорта:
    add     — только добавление новых (существующие номера пропускаются);
    upsert  — добавить новые + обновить существующие по catalog_number.

Обложки берутся:
    - из ZIP-архива, загруженного вместе с CSV (колонка «URL обложки» —
      имя файла внутри архива);
    - либо по http(s)-URL из той же колонки.

Построчная обработка ошибок: корректные строки импортируются, для
некорректных формируется отчёт (номер строки, причина).
"""

import csv
import io
import re
import zipfile
from urllib.request import urlopen

from django.core.files.base import ContentFile
from django.db import transaction

from catalog.models import Book, Category

# Канонические заголовки колонок (экспорт пишет именно их)
HEADERS = [
    "Название",
    "Автор",
    "Каталожный номер",
    "Год",
    "Категория",
    "Описание",
    "URL обложки",
]

MAX_COVER_BYTES = 5 * 1024 * 1024  # 5 МБ, как в форме админки (этап 5)
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# Синонимы заголовков колонок (для файлов «из Excel» и произвольных разметок)
_ALIASES = {
    "title": ["название", "заголовок", "книга", "title"],
    "author": ["автор", "author"],
    "catalog_number": ["каталожный номер", "каталожный", "номер", "инвентарный номер", "catalog_number", "catalog number"],
    "year": ["год", "год издания", "year"],
    "category": ["категория", "раздел", "предмет", "category"],
    "description": ["описание", "аннотация", "description"],
    "cover_url": ["url обложки", "обложка", "cover", "cover url", "ссылка на обложку", "файл обложки"],
}


def _norm_header(h: str) -> str:
    return re.sub(r"\s+", " ", (h or "").strip().lower())


def detect_dialect(text: str):
    """Автоопределение разделителя: ';' или ',' (первое содержательное поле не режем)."""
    sample = "\n".join(text.splitlines()[:10])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,")
        delim = dialect.delimiter
    except csv.Error:
        first_line = text.splitlines()[0] if text.splitlines() else ""
        delim = ";" if first_line.count(";") >= first_line.count(",") else ","
    return delim


def decode_bytes(raw: bytes) -> str:
    """UTF-8 c BOM → UTF-8; иначе подбор кодировки с понятной ошибкой."""
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(
        "Не удалось прочитать файл: поддерживаются кодировки UTF-8 и UTF-8 с BOM."
    )


class ImportReport:
    """Сводка + построчный отчёт ошибок."""

    def __init__(self):
        self.added = 0
        self.updated = 0
        self.errors = []  # список dict(row=..., reason=...)

    @property
    def error_count(self):
        return len(self.errors)

    def as_context(self):
        return {
            "added": self.added,
            "updated": self.updated,
            "errors": self.errors,
            "error_count": self.error_count,
            "total_ok": self.added + self.updated,
        }


def _map_columns(fieldnames):
    mapping = {}
    for fn in fieldnames or []:
        key = _norm_header(fn)
        for field, aliases in _ALIASES.items():
            if key in (_norm_header(a) for a in aliases):
                mapping[fn] = field
                break
    return mapping


def _clean_year(value):
    value = (value or "").strip()
    if not value:
        return None
    if not re.fullmatch(r"\d{4}", value):
        raise ValueError(f"некорректный год «{value}» (ожидается 4 цифры)")
    year = int(value)
    if not (1000 <= year <= 2100):
        raise ValueError(f"год «{year}» вне диапазона 1000–2100")
    return year


def _owner_id(request):
    from catalog.models import User
    admin = User.objects.filter(role=User.Role.ADMIN, is_blocked=False).order_by("pk").first()
    return request.user.pk if request.user.is_authenticated else (admin.pk if admin else None)


def _apply_cover(book, cover_ref, zip_files, report_row=None):
    """Загружает обложку: из ZIP-архива по имени файла либо по http(s)-URL."""
    ref = (cover_ref or "").strip()
    if not ref:
        return
    ext = "." + ref.rsplit(".", 1)[-1].lower() if "." in ref else ""
    if ext not in ALLOWED_IMAGE_EXT:
        raise ValueError(f"обложка «{ref}»: неподдерживаемый тип файла (только jpg/png/webp/gif)")

    data = None
    if zip_files is not None:
        name = ref.replace("\\", "/").split("/")[-1]
        if name in zip_files:
            data = zip_files[name]
    if data is None and re.match(r"^https?://", ref, re.I):
        try:
            with urlopen(ref, timeout=10) as resp:  # noqa: S310 — только http(s)
                payload = resp.read(MAX_COVER_BYTES + 1)
            if len(payload) > MAX_COVER_BYTES:
                raise ValueError("обложка: размер файла превышает 5 МБ")
            data = payload
        except ValueError:
            raise
        except Exception as exc:  # URLError и прочее
            raise ValueError(f"не удалось скачать обложку по URL ({exc.__class__.__name__})")
    if data is None:
        raise ValueError(f"обложка «{ref}» не найдена (нет в ZIP и не URL)")
    if len(data) > MAX_COVER_BYTES:
        raise ValueError("обложка: размер файла превышает 5 МБ")

    safe_name = re.sub(r"[^\w.\-]+", "_", ref.replace("\\", "/").split("/")[-1])
    book.cover.save(f"{safe_name}", ContentFile(data), save=True)


def import_csv(csv_bytes: bytes, mode: str, request, zip_bytes: bytes | None = None) -> ImportReport:
    """Импортирует CSV; возвращает ImportReport.

    mode: "add" | "upsert". Ошибочные строки пропускаются (с отчётом),
    корректные импортируются.
    """
    report = ImportReport()
    text = decode_bytes(csv_bytes)
    delim = detect_dialect(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    colmap = _map_columns(reader.fieldnames)

    if "title" not in colmap.values() or "author" not in colmap.values():
        raise ValueError(
            "В CSV не найдены обязательные колонки «Название» и «Автор». "
            f"Обнаружены колонки: {reader.fieldnames}"
        )

    # Файлы из ZIP (если приложен)
    zip_files = None
    if zip_bytes:
        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        except zipfile.BadZipFile:
            raise ValueError("Архив обложек повреждён или не является ZIP-файлом.")
        zip_files = {}
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/").split("/")[-1]
            if name.lower().endswith(tuple(ALLOWED_IMAGE_EXT)):
                zip_files[name] = zf.read(info)

    cat_cache = {c.name: c for c in Category.objects.all()}
    owner_pk = _owner_id(request)
    seen_numbers = set()  # каталожные номера, уже встреченные в этом файле

    for row_no, row in enumerate(reader, start=2):  # строка 1 — заголовок
        vals = {}
        for src, field in colmap.items():
            vals[field] = (row.get(src) or "").strip()

        problems = []
        title = vals.get("title", "")
        author = vals.get("author", "")
        if not title:
            problems.append("пустое название")
        if not author:
            problems.append("пустой автор")
        try:
            year = _clean_year(vals.get("year"))
        except ValueError as exc:
            problems.append(str(exc))
            year = None
        cat_name = vals.get("category", "") or "Без категории"

        cn = vals.get("catalog_number", "")
        # дубликат номера внутри самого файла — ошибка строки (в любом режиме)
        if cn and cn in seen_numbers:
            report.errors.append({
                "row": row_no,
                "reason": f"дубль каталожного номера «{cn}» внутри файла",
            })
            continue
        existing = Book.objects.filter(catalog_number=cn).first() if cn else None
        # дубль номера в базе (в режиме upsert строка не обновляется, если
        # содержимое идентичен — засчитываем как ошибку-дубль)
        if existing and not problems:
            same = (
                existing.title == title
                and existing.author == author
                and existing.year == year
                and (existing.description or "") == (vals.get("description") or "")
            )
            if same:
                report.errors.append({
                    "row": row_no,
                    "reason": f"книга с каталожным номером «{cn}» уже существует без изменений",
                })
                continue
        if existing and mode == "add":
            report.errors.append({
                "row": row_no,
                "reason": f"книга с каталожным номером «{cn}» уже существует — пропущено (режим «добавить новые»)",
            })
            continue

        if problems:
            report.errors.append({"row": row_no, "reason": "; ".join(problems)})
            continue
        if cn:
            seen_numbers.add(cn)

        try:
            with transaction.atomic():
                book = existing or Book()
                # снимок «до» для подсчёта реально изменённых строк (upsert)
                old_state = None
                if book.pk is not None:
                    old_state = (book.title, book.author, book.catalog_number,
                                 book.year, book.category_id, book.description)
                book.title = title
                book.author = author
                if cn:
                    book.catalog_number = cn
                book.year = year
                if cat_name not in cat_cache:
                    cat_cache[cat_name] = Category.objects.create(name=cat_name)
                book.category = cat_cache[cat_name]
                # описание обновляем только если в CSV оно заполнено —
                # иначе round-trip «пустая ячейка» затирал бы существующий текст
                if vals.get("description"):
                    book.description = vals["description"]
                if book.pk is None:
                    book.owner_id = owner_pk
                    book.save()
                    report.added += 1
                else:
                    book.save()
                    new_state = (book.title, book.author, book.catalog_number,
                                 book.year, book.category_id, book.description)
                    if new_state != old_state:
                        report.updated += 1
                _apply_cover(book, vals.get("cover_url", ""), zip_files)
        except Exception as exc:  # noqa: BLE001 — построчный отчёт
            report.errors.append({"row": row_no, "reason": f"ошибка сохранения: {exc}"})

    return report


def export_books_csv(queryset=None) -> str:
    """Выгрузка каталога в CSV (UTF-8; вызывающий код оборачивает в BOM).

    Колонки = колонкам импорта (round-trip). Если queryset передан —
    выгружается отфильтрованная выборка, иначе — вся база.
    """
    qs = (queryset if queryset is not None else Book.objects.all())
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    writer.writerow(HEADERS)
    for b in qs.order_by("catalog_number"):
        cover_url = b.cover.url if b.cover else ""
        writer.writerow([
            b.title,
            b.author,
            b.catalog_number,
            b.year or "",
            b.category.name,
            b.description,
            cover_url,
        ])
    return buf.getvalue()
