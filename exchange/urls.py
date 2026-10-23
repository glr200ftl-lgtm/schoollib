from django.urls import path

from . import views

app_name = "exchange"

urlpatterns = [
    path("exchange/", views.exchange_list, name="list"),
    path("exchange/new", views.ad_create, name="create"),
    path("exchange/<int:pk>/", views.ad_detail, name="detail"),
    path("exchange/<int:pk>/edit", views.ad_edit, name="edit"),
    path("exchange/<int:pk>/delete", views.ad_delete, name="delete"),
    path("exchange/<int:pk>/archive", views.ad_archive, name="archive"),
]
