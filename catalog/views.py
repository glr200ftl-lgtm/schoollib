"""Представления каталога (Этап 1: заглушки страниц / и /catalog)."""

from django.shortcuts import render

from .models import Book, Category


def home(request):
    """Главная страница: краткая сводка (каркас, без функциональности)."""
    context = {
        "books_count": Book.objects.count(),
        "categories_count": Category.objects.count(),
    }
    return render(request, "catalog/home.html", context)


def catalog(request):
    """Каталог книг — на этапе 1 просто список из seed-данных."""
    books = Book.objects.select_related("category", "owner").all()
    categories = Category.objects.all()
    context = {"books": books, "categories": categories}
    return render(request, "catalog/catalog.html", context)
