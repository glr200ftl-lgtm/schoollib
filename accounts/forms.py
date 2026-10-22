"""Формы раздела аутентификации (Этап 2)."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

User = get_user_model()


class RegisterForm(forms.ModelForm):
    """Регистрация: ФИО, e-mail, пароль ×2, класс."""

    password1 = forms.CharField(
        label="Пароль", widget=forms.PasswordInput(attrs={"autofocus": True})
    )
    password2 = forms.CharField(label="Повторите пароль", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ["full_name", "email", "grade"]
        widgets = {
            "full_name": forms.TextInput(attrs={"placeholder": "Иванов Иван Иванович"}),
            "email": forms.EmailInput(attrs={"placeholder": "you@school.ru"}),
            "grade": forms.TextInput(attrs={"placeholder": "9А"}),
        }

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(
                "Пользователь с таким e-mail уже зарегистрирован. "
                "Войдите или восстановите пароль."
            )
        return email

    def clean(self):
        super().clean()
        p1 = self.cleaned_data.get("password1")
        p2 = self.cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            raise ValidationError("Пароли не совпадают.")
        if p1:
            try:
                validate_password(p1)
            except ValidationError as e:
                self.add_error("password1", e.messages)
        return self.cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = user.email  # логин = e-mail
        user.role = User.Role.STUDENT
        user.set_password(self.cleaned_data["password1"])  # в БД — только хеш
        if commit:
            user.save()
        return user


class LoginForm(forms.Form):
    """Вход: логин или e-mail + пароль."""

    username = forms.CharField(
        label="Логин или e-mail",
        widget=forms.TextInput(attrs={"autofocus": True}),
    )
    password = forms.CharField(label="Пароль", widget=forms.PasswordInput)


class ProfileForm(forms.ModelForm):
    """Правка профиля ученика: ФИО, класс, контакт (e-mail)."""

    class Meta:
        model = User
        fields = ["full_name", "grade", "email"]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Этот e-mail уже используется другим пользователем.")
        return email


class PasswordChangeForm(forms.Form):
    """Смена пароля: текущий + новый ×2."""

    old_password = forms.CharField(label="Текущий пароль", widget=forms.PasswordInput)
    new_password1 = forms.CharField(
        label="Новый пароль", widget=forms.PasswordInput
    )
    new_password2 = forms.CharField(
        label="Повторите новый пароль", widget=forms.PasswordInput
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_old_password(self):
        old = self.cleaned_data["old_password"]
        if not self.user.check_password(old):
            raise ValidationError("Текущий пароль указан неверно.")
        return old

    def clean(self):
        super().clean()
        p1 = self.cleaned_data.get("new_password1")
        p2 = self.cleaned_data.get("new_password2")
        if p1 and p2 and p1 != p2:
            raise ValidationError("Новые пароли не совпадают.")
        if p1:
            try:
                validate_password(p1, self.user)
            except ValidationError as e:
                self.add_error("new_password1", e.messages)
        return self.cleaned_data

    def save(self):
        self.user.set_password(self.cleaned_data["new_password1"])
        self.user.save(update_fields=["password"])
        return self.user


class PasswordResetRequestForm(forms.Form):
    """Запрос восстановления пароля по e-mail."""

    email = forms.EmailField(label="Ваш e-mail")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        qs = User.objects.filter(email__iexact=email)
        if not qs.exists():
            raise ValidationError("Пользователь с таким e-mail не найден.")
        return email

    def get_user(self):
        return User.objects.get(email__iexact=self.cleaned_data["email"])


class SetPasswordForm(forms.Form):
    """Установка нового пароля по ссылке из письма."""

    new_password1 = forms.CharField(
        label="Новый пароль", widget=forms.PasswordInput(attrs={"autofocus": True})
    )
    new_password2 = forms.CharField(
        label="Повторите пароль", widget=forms.PasswordInput
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        super().clean()
        p1 = self.cleaned_data.get("new_password1")
        p2 = self.cleaned_data.get("new_password2")
        if p1 and p2 and p1 != p2:
            raise ValidationError("Пароли не совпадают.")
        if p1:
            try:
                validate_password(p1, self.user)
            except ValidationError as e:
                self.add_error("new_password1", e.messages)
        return self.cleaned_data

    def save(self):
        self.user.set_password(self.cleaned_data["new_password1"])
        self.user.save(update_fields=["password"])
        return self.user
