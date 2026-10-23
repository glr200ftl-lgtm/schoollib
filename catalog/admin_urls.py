from django.urls import path

from . import admin_views

app_name = "catalog_admin"

urlpatterns = [
    path("admin/books/", admin_views.book_list, name="book_list"),
    path("admin/books/add", admin_views.book_create, name="book_create"),
    path("admin/books/<int:pk>/edit", admin_views.book_edit, name="book_edit"),
    path("admin/books/<int:pk>/delete", admin_views.book_delete, name="book_delete"),
    path("admin/categories/", admin_views.category_list, name="category_list"),
    path("admin/categories/add", admin_views.category_create, name="category_create"),
    path("admin/categories/<int:pk>/edit", admin_views.category_edit, name="category_edit"),
    path("admin/categories/<int:pk>/delete", admin_views.category_delete, name="category_delete"),
    path("admin/import", admin_views.csv_import, name="import"),
    path("admin/export", admin_views.csv_export, name="export"),
]

# Явные строки для проверок middleware (см. accounts/access.py EXEMPT_PATHS)
EXEMPT_URLS = [p.pattern for p in urlpatterns]
