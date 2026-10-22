"""Представления аутентификации (Этап 2).

Регистрация с подтверждением e-mail (в dev — ссылка в консоль/лог),
вход/выход, восстановление пароля, профиль, /my.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import (
    get_user_model,
    login,
    logout,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMessage
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .forms import (
    LoginForm,
    PasswordChangeForm,
    PasswordResetRequestForm,
    ProfileForm,
    RegisterForm,
    SetPasswordForm,
)
from .tokens import account_token_generator

User = get_user_model()


# --- Служебное: отправка письма ---------------------------------------

def build_absolute_uri(request, path):
    return f"{settings.SITE_SCHEME}://{request.get_host()}{path}"


def send_mail_with_log(subject, template_name, context, to_email, request):
    """Отправляет письмо; в dev-режиме дополнительно пишет ссылку в лог/консоль."""
    body = render_to_string(template_name, context)
    mail = EmailMessage(subject=subject, body=body, to=[to_email], from_email=settings.DEFAULT_FROM_EMAIL)
    try:
        mail.send(fail_silently=False)
        sent = True
    except Exception:  # в dev без SMTP — не роняем регистрацию
        sent = False
    logger = __import__("logging").getLogger("accounts.mail")
    link = context.get("link", "")
    logger.info("Письмо «%s» для %s%s: %s", subject, to_email, "" if sent else " (SMTP недоступен, ссылка ниже)", link)
    print(f"\n[MAIL] Кому: {to_email}\n[MAIL] Тема: {subject}\n[MAIL] Ссылка: {link}\n")
    return sent


# --- Регистрация --------------------------------------------------------

def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:profile")
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            token = account_token_generator.make_token(user)
            link = build_absolute_uri(
                request,
                reverse("accounts:confirm_email", args=[urlsafe_base64_encode(force_bytes(user.pk)), token]),
            )
            send_mail_with_log(
                subject="Подтвердите регистрацию в школьной библиотеке",
                template_name="accounts/email_confirm.txt",
                context={"user": user, "link": link},
                to_email=user.email,
                request=request,
            )
            messages.success(
                request,
                "Аккаунт создан. Мы отправили письмо со ссылкой подтверждения на "
                f"{user.email}. В режиме разработки ссылка также выведена в консоль.",
            )
            return redirect("accounts:login")
    else:
        form = RegisterForm()
    return render(request, "accounts/register.html", {"form": form})


def confirm_email(request, uid_b64, token):
    user = get_object_or_404(User, pk=_decode_uid(uid_b64))
    if not account_token_generator.check_token(user, token):
        return render(
            request,
            "accounts/result.html",
            {"title": "Ссылка недействительна", "text": "Срок действия ссылки истёк или она уже была использована. Попробуйте запросить подтверждение снова."},
        )
    if not user.email_confirmed:
        user.email_confirmed = True
        user.save(update_fields=["email_confirmed"])
    return render(
        request,
        "accounts/result.html",
        {"title": "E-mail подтверждён", "text": f"Готово! Подтверждение для {user.email} выполнено. Теперь можно войти."},
    )


def _decode_uid(uid_b64):
    try:
        return int(urlsafe_base64_decode(uid_b64))
    except (ValueError, TypeError):
        return 0


# --- Вход / выход --------------------------------------------------------

def user_login(request):
    if request.user.is_authenticated:
        return redirect("accounts:profile")
    form = LoginForm(request.POST or None)
    error = None
    if request.method == "POST" and form.is_valid():
        identifier = form.cleaned_data["username"]
        password = form.cleaned_data["password"]
        user = User.objects.filter(username=identifier).first()
        if user is None and "@" in identifier:
            user = User.objects.filter(email__iexact=identifier).first()
        if user is not None and user.check_password(password):
            if user.is_blocked or not user.is_active:
                error = "Ваша учётная запись заблокирована. Обратитесь к администратору библиотеки."
            elif not user.email_confirmed:
                error = (
                    "E-mail не подтверждён. Проверьте почту (в dev-режиме ссылка "
                    "выведена в консоль сервера) и перейдите по ней."
                )
            else:
                login(request, user, backend="accounts.backends.EmailOrUsernameModelBackend")
                nxt = request.GET.get("next")
                messages.success(request, f"Добро пожаловать, {user.full_name}!")
                return redirect(nxt or "accounts:profile")
        else:
            error = "Неверный логин (e-mail) или пароль."
    return render(request, "accounts/login.html", {"form": form, "error": error})


@login_required
def user_logout(request):
    logout(request)
    messages.info(request, "Вы вышли из аккаунта.")
    return redirect("catalog:home")


# --- Восстановление пароля ------------------------------------------------

def password_reset_request(request):
    sent = False
    if request.method == "POST":
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            user = form.get_user()
            token = default_token_generator.make_token(user)
            link = build_absolute_uri(
                request,
                reverse("accounts:password_reset_confirm", args=[urlsafe_base64_encode(force_bytes(user.pk)), token]),
            )
            send_mail_with_log(
                subject="Восстановление пароля — школьная библиотека",
                template_name="accounts/email_password_reset.txt",
                context={"user": user, "link": link},
                to_email=user.email,
                request=request,
            )
            sent = True
    else:
        form = PasswordResetRequestForm()
    return render(request, "accounts/password_reset.html", {"form": form, "sent": sent})


def password_reset_confirm(request, uid_b64, token):
    user = get_object_or_404(User, pk=_decode_uid(uid_b64))
    if not default_token_generator.check_token(user, token):
        return render(
            request,
            "accounts/result.html",
            {"title": "Ссылка недействительна", "text": "Срок действия ссылки истёк или она уже использована. Запросите восстановление пароля заново."},
        )
    if request.method == "POST":
        form = SetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Пароль изменён. Теперь войдите с новым паролем.")
            return redirect("accounts:login")
    else:
        form = SetPasswordForm(user)
    return render(request, "accounts/password_reset_confirm.html", {"form": form})


# --- Профиль / мой кабинет --------------------------------------------------

@login_required
def my(request):
    """Кабинет пользователя (/my) — доступен только авторизованным."""
    books = request.user.books.select_related("category").order_by("-created_at")
    ads = request.user.ads.select_related("book").order_by("-created_at")
    return render(request, "accounts/my.html", {"books": books, "ads": ads})


@login_required
def profile(request):
    """Просмотр и правка профиля: ФИО, класс, контакт (e-mail)."""
    user = request.user
    pform = ProfileForm(instance=user, prefix="p")
    if request.method == "POST" and "profile_submit" in request.POST:
        pform = ProfileForm(request.POST, instance=user, prefix="p")
        if pform.is_valid():
            old_email = user.email
            saved = pform.save(commit=False)
            email_changed = saved.email.lower() != (old_email or "").lower()
            if email_changed:
                saved.email_confirmed = False
            saved.save()
            if email_changed:
                token = account_token_generator.make_token(saved)
                link = build_absolute_uri(
                    request,
                    reverse("accounts:confirm_email", args=[urlsafe_base64_encode(force_bytes(saved.pk)), token]),
                )
                send_mail_with_log(
                    subject="Подтвердите новый e-mail",
                    template_name="accounts/email_confirm.txt",
                    context={"user": saved, "link": link},
                    to_email=saved.email,
                    request=request,
                )
                messages.success(
                    request,
                    "Профиль сохранён. На новый e-mail отправлена ссылка подтверждения.",
                )
            else:
                messages.success(request, "Профиль сохранён.")
            return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"pform": pform})


@login_required
def password_change(request):
    user = request.user
    if request.method == "POST":
        form = PasswordChangeForm(user, request.POST)
        if form.is_valid():
            form.save()
            # обновляем сессию, чтобы не «выбивало»
            login(request, user)
            messages.success(request, "Пароль успешно изменён.")
            return redirect("accounts:profile")
    else:
        form = PasswordChangeForm(user)
    return render(request, "accounts/password_change.html", {"form": form})
