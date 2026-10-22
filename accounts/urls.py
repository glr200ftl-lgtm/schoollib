"""URL-маршруты раздела аутентификации (Этап 2)."""

from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.user_login, name="login"),
    path("logout/", views.user_logout, name="logout"),
    path(
        "confirm-email/<str:uid_b64>/<str:token>/",
        views.confirm_email,
        name="confirm_email",
    ),
    path("password-reset/", views.password_reset_request, name="password_reset"),
    path(
        "password-reset/confirm/<str:uid_b64>/<str:token>/",
        views.password_reset_confirm,
        name="password_reset_confirm",
    ),
    path("my/", views.my, name="my"),
    path("profile/", views.profile, name="profile"),
    path("profile/password/", views.password_change, name="password_change"),
]
