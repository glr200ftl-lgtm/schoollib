from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("", views.home, name="home"),
    path("catalog/", views.catalog, name="catalog"),
    path("catalog/<int:pk>/", views.category_books, name="category"),
    path("book/<int:pk>/", views.book_detail, name="book_detail"),
]
