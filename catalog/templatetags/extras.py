"""Вспомогательные template-фильтры."""

from django import template

register = template.Library()


@register.filter(name="dict_access")
def dict_access(d, key):
    """Доступ к значению словаря по ключу-строке: {{ counts|dict_access:value }}."""
    try:
        return d[key]
    except (KeyError, TypeError):
        return ""
