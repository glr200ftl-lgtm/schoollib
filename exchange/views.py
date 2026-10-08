"""Представления раздела обмена (Этап 1: заглушка страницы /exchange)."""

from django.shortcuts import render


def exchange(request):
    """Страница объявлений об обмене — на этапе 1 существует как заглушка."""
    return render(request, "exchange/exchange.html", {})
