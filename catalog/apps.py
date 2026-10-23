import sqlite3

from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _unicode_lower(connection, **kwargs):
    """SQLite по умолчанию фолдит LOWER() только для ASCII — из-за этого
    __icontains не находит кириллицу в нижнем/верхнем регистре.
    Регистрируем Unicode-совместимый lower() на каждом новом соединении."""
    if connection.vendor != "sqlite":
        return
    raw = connection.connection
    try:
        if isinstance(raw, sqlite3.Connection):
            raw.create_function(
                "LOWER", -1, lambda s: s.lower() if isinstance(s, str) else s,
                deterministic=True,
            )
        else:  # пул соединений (Django >= 5.1): регистрируем на всех активных conns
            for conn in getattr(raw, "connections", []):
                if isinstance(conn, sqlite3.Connection):
                    conn.create_function(
                        "LOWER", -1, lambda s: s.lower() if isinstance(s, str) else s,
                        deterministic=True,
                    )
    except Exception:
        pass


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "catalog"
    verbose_name = "Каталог книг"

    def ready(self):
        connection_created.connect(_unicode_lower)
