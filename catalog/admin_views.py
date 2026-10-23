"""Административное управление каталогом (Этап 5 + Этап 6: CSV-импорт/экспорт).

Разметка маршрутов: /admin/books, /admin/books/<id>/edit,
/admin/books/add, /admin/books/<id>/delete,
/admin/categories, /admin/categories/<action>,
/admin/import — загрузка CSV (+ZIP обложек) с предпросмотром,
/admin/export — выгрузка каталога (весь или отфильтрованный выборочно).

Доступ только для роли admin (через декоратор @admin_required).
"""


from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from accounts.access import admin_required
from catalog.csv_io import export_books_csv, import_csv
from catalog.forms import AdminBookForm, CategoryForm
from catalog.models import Book, Category
from catalog.views import _search_filter


class _RollbackDryRun(Exception):
    """Служебное исключение для отката dry-run транзакции предпросмотра."""


# Ограничение размера загружаемых файлов импорта (защита от случайных «всё в одном»):
MAX_IMPORT_FILE_MB = 20


@admin_required
def book_list(request):
    """Список книг с поиском и фильтром по категории."""
    books = Book.objects.select_related("category", "owner").order_by("-created_at")
    q = request.GET.get("q", "").strip()
    cat_id = request.GET.get("category", "").strip()

    if q:
        books = books.filter(_search_filter(q))
    if cat_id.isdigit():
        books = books.filter(category_id=int(cat_id))

    paginator = Paginator(books, per_page=24)
    page_obj = paginator.get_page(request.GET.get("page"))

    categories = Category.objects.all().order_by("name")
    context = {
        "page_obj": page_obj,
        "total_count": paginator.count,
        "categories": categories,
        "q": q,
        "selected_category": int(cat_id) if cat_id.isdigit() else None,
    }
    return render(request, "catalog/admin_books.html", context)


@admin_required
def book_create(request):
    """Добавление книги."""
    form = AdminBookForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        book = form.save(commit=False)
        book.owner = request.user
        book.save()
        return redirect(reverse("catalog_admin:book_list"))
    return render(request, "catalog/admin_book_form.html", {"form": form, "is_new": True})


@admin_required
def book_edit(request, pk):
    """Редактирование книги."""
    book = get_object_or_404(Book, pk=pk)
    form = AdminBookForm(request.POST or None, request.FILES or None, instance=book)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect(reverse("catalog_admin:book_list"))
    return render(request, "catalog/admin_book_form.html", {"form": form, "book": book, "is_new": False})


@admin_required
def book_delete(request, pk):
    """Удаление книги с подтверждением (GET — форма, POST — действие)."""
    book = get_object_or_404(Book, pk=pk)
    if request.method == "POST":
        book.delete()
        return redirect(reverse("catalog_admin:book_list"))
    return render(request, "catalog/confirm_delete.html", {"object": book, "cancel_url": reverse("catalog_admin:book_list")})


@admin_required
def category_list(request):
    """Список категорий со счётчиками книг."""
    cats = Category.objects.order_by("name")
    # счётчик книг в каждой категории
    from django.db.models import Count
    cats = cats.annotate(book_count=Count("books"))
    return render(request, "catalog/admin_categories.html", {"categories": cats})


@admin_required
def category_create(request):
    """Создание категории."""
    form = CategoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect(reverse("catalog_admin:category_list"))
    return render(request, "catalog/admin_category_form.html", {"form": form, "is_new": True})


@admin_required
def category_edit(request, pk):
    """Переименование категории."""
    cat = get_object_or_404(Category, pk=pk)
    form = CategoryForm(request.POST or None, instance=cat)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect(reverse("catalog_admin:category_list"))
    return render(request, "catalog/admin_category_form.html", {"form": form, "category": cat, "is_new": False})


@admin_required
def category_delete(request, pk):
    """Удаление категории. Непустая категория не удаляется (on_delete=PROTECT)."""
    cat = get_object_or_404(Category, pk=pk)
    book_count = cat.books.count()
    if request.method == "POST":
        if book_count:
            return render(
                request,
                "catalog/admin_category_delete_blocked.html",
                {"category": cat, "book_count": book_count},
                status=400,
            )
        cat.delete()
        return redirect(reverse("catalog_admin:category_list"))
    return render(
        request,
        "catalog/confirm_delete.html",
        {"object": cat, "cancel_url": reverse("catalog_admin:category_list")},
    )


# ---------------------------------------------------------------------------
# Этап 6: CSV-импорт / экспорт
# ---------------------------------------------------------------------------

@admin_required
def csv_import(request):
    """Загрузка CSV (+ при желании ZIP с обложками) с предпросмотром и применением.

    Поток:
      1) GET /admin/import — форма;
      2) POST с файлом (без apply) — валидация и предпросмотр-сводка
         «будет добавлено N, обновлено M, ошибок K»; данные НЕ изменяются
         (dry-run в откатываемой транзакции);
      3) POST c apply=yes + confirm_mode (тот же файл выбран повторно) —
         применение импорта.
    """
    if request.method == "POST":
        csv_file = request.FILES.get("csv_file")
        zip_file = request.FILES.get("zip_file")
        mode = request.POST.get("mode", "") or request.POST.get("confirm_mode", "add")
        apply_ = request.POST.get("apply", "no") == "yes"

        if not csv_file:
            return render(request, "catalog/admin_import.html", {
                "mode": mode, "form_error": "Выберите CSV-файл для импорта.",
            })
        if mode not in ("add", "upsert"):
            mode = "add"

        csv_bytes = csv_file.read()
        zip_bytes = zip_file.read() if zip_file else None

        limit = MAX_IMPORT_FILE_MB * 1024 * 1024
        if len(csv_bytes) > limit or (zip_bytes and len(zip_bytes) > limit):
            return render(request, "catalog/admin_import.html", {
                "mode": mode,
                "form_error": f"Файл больше {MAX_IMPORT_FILE_MB} МБ — разбейте импорт на части.",
            })

        # Проверка формата (кодировка/разделитель/колонки) — до любых записей.
        from catalog.csv_io import decode_bytes, detect_dialect
        try:
            text = decode_bytes(csv_bytes)
            detect_dialect(text)
        except ValueError as exc:
            return render(request, "catalog/admin_import.html", {
                "mode": mode, "form_error": str(exc),
            })

        # Применение: пользователь подтвердил предпросмотр и выбрал тот же файл
        # повторно (stateless-подтверждение без хранения файла на сервере).
        if apply_ and request.POST.get("confirm_mode") in ("add", "upsert"):
            report = import_csv(csv_bytes, mode, request, zip_bytes)
            return render(request, "catalog/admin_import_result.html", {
                "report": report.as_context(), "mode": mode,
            })

        # Предпросмотр: dry-run в транзакции с принудительным откатом —
        # сводка формируется по реальному состоянию БД, но ничего не меняется.
        try:
            with transaction.atomic():
                preview = import_csv(csv_bytes, mode, request, zip_bytes)
                raise _RollbackDryRun
        except _RollbackDryRun:
            pass

        return render(request, "catalog/admin_import.html", {
            "mode": mode,
            "preview": report_preview_dict(preview),
            "file_name": csv_file.name,
            "zip_name": zip_file.name if zip_file else "",
        })

    return render(request, "catalog/admin_import.html", {"mode": "add"})


def report_preview_dict(report):
    d = report.as_context()
    d["will_add"] = d["added"]
    d["will_update"] = d["updated"]
    return d


@admin_required
def csv_export(request):
    """Выгрузка каталога в CSV (UTF-8 с BOM).

    Параметры ?q= и ?category= — как в списке книг: выгружается либо вся
    база, либо отфильтрованная выборка. Колонки = колонкам импорта (round-trip).
    """
    books = Book.objects.select_related("category").order_by("catalog_number")
    q = request.GET.get("q", "").strip()
    cat_id = request.GET.get("category", "").strip()
    if q:
        books = books.filter(_search_filter(q))
    if cat_id.isdigit():
        books = books.filter(category_id=int(cat_id))

    content = export_books_csv(books)
    response = HttpResponse(
        "\ufeff" + content,  # UTF-8 BOM для корректного открытия в Excel
        content_type="text/csv; charset=utf-8",
    )
    from django.utils import timezone
    stamp = timezone.localtime().strftime("%Y-%m-%d")
    suffix = "-filtered" if (q or cat_id.isdigit()) else "-all"
    response["Content-Disposition"] = f'attachment; filename="catalog_{stamp}{suffix}.csv"'
    return response
