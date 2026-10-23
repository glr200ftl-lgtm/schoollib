"""Представления публичного каталога (Этап 3: список, фильтры, поиск, карточка книги)."""

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import connections
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from .models import Book, Category

BOOKS_PER_PAGE = 24


def _norm(value: str) -> str:
    """Unicode-корректный нижний регистр (SQLite фолдит только ASCII)."""
    return value.lower()


def _search_filter(query: str):
    """Частичное совпадение по названию ИЛИ автору, регистронезависимо.

    Django-lookup `icontains` на SQLite фолдит только ASCII (кириллица не
    приводится к нижнему регистру функцией LOWER() в SQLite), поэтому для
    SQLite сравниваем LOWER(поле) и LOWER(запрос) через Trunc/Func — но
    надёжнее всего сделать нормализацию на уровне Python: выбираем id
    подходящих книг списком (каталог школьный — объёмы небольшие).
    Для PostgreSQL используем обычный icontains (там фолдинг корректный).
    """
    q = _norm(query)
    if connections["default"].vendor == "sqlite":
        ids = [b.pk for b in Book.objects.all()
               if q in _norm(b.title) or q in _norm(b.author)]
        return Q(pk__in=ids)
    return Q(title__icontains=q) | Q(author__icontains=q)


def _book_list(request, queryset, extra_context=None):
    """Общая сборка страницы со списком книг: фильтр по категориям + поиск + пагинация.

    Параметры запроса:
      q          — поисковая строка (название ИЛИ автор, частичное совпадение, без учёта регистра);
      categories — список id категорий (фильтр со счётчиками);
      page       — номер страницы.
    Фильтр и поиск комбинируются.
    """
    selected_ids = [c for c in request.GET.getlist("categories") if c.isdigit()]
    query = request.GET.get("q", "").strip()

    if query:
        search_q = _search_filter(query)
        queryset = queryset.filter(search_q)

    # База для счётчиков категорий: все книги, подходящие под поиск
    counter_qs = Book.objects.all()
    if query:
        counter_qs = counter_qs.filter(search_q)

    if selected_ids:
        queryset = queryset.filter(category_id__in=selected_ids)
        # при активном фильтре в сайдбаре показываем только выбранные категории
        counter_qs = counter_qs.filter(category_id__in=selected_ids)

    # Категории со счётчиками (совпадают с выдачей при том же поиске/фильтре)
    categories = (
        counter_qs.order_by()
        .values("category__id", "category__name")
        .annotate(books_count=Count("id"))
        .order_by("category__name")
    )

    paginator = Paginator(queryset.order_by("title"), BOOKS_PER_PAGE)
    page_number = request.GET.get("page")
    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.get_page(1)
    except EmptyPage:
        page_obj = paginator.get_page(paginator.num_pages)

    context = {
        "page_obj": page_obj,
        "categories": categories,
        "selected_ids": selected_ids,
        "query": query,
        "total_count": paginator.count,
    }
    if extra_context:
        context.update(extra_context)
    return context


def home(request):
    """Главная страница: краткая сводка."""
    context = {
        "books_count": Book.objects.count(),
        "categories_count": Category.objects.count(),
    }
    return render(request, "catalog/home.html", context)


def catalog(request):
    """/catalog: сетка карточек, пагинация 24/стр, фильтр по категориям со счётчиками, поиск."""
    context = _book_list(request, Book.objects.select_related("category", "owner").all())
    return render(request, "catalog/catalog.html", context)


def category_books(request, pk):
    """/catalog/{id}: книги категории + счётчик; фильтр и поиск внутри категории."""
    category = get_object_or_404(Category, pk=pk)
    base = Book.objects.select_related("category", "owner").filter(category=category)
    context = _book_list(
        request,
        base,
        extra_context={
            "category": category,
            "current_category_count": base.count(),
        },
    )
    context["selected_ids"] = [str(category.pk)]
    return render(request, "catalog/catalog.html", context)


def book_detail(request, pk):
    """/book/{id}: обложка (или заглушка), название, автор, категория, каталожный номер, год, описание, статус наличия."""
    book = get_object_or_404(
        Book.objects.select_related("category", "owner"), pk=pk
    )
    return render(request, "catalog/book_detail.html", {"book": book})
