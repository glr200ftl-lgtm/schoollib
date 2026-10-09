from django.urls import path

from . import views

app_name = "exchange"

urlpatterns = [
    path("exchange/", views.exchange, name="exchange"),
]
