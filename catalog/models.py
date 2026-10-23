from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    """Менеджер пользователей: создание обычного пользователя и администратора."""

    def create_user(self, username, full_name="", password=None, **extra_fields):
        if not username:
            raise ValueError("Логин обязателен.")
        email = self.normalize_email(extra_fields.pop("email", ""))
        user = self.model(username=username, full_name=full_name, email=email, **extra_fields)
        if password:
            user.set_password(password)  # сохраняем только хеш
        else:
            user.password = ""
        user.save(using=self._db)
        return user

    def create_superuser(self, username, full_name="", password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_blocked", False)
        return self.create_user(username, full_name, password, **extra_fields)


class User(AbstractBaseUser):
    """Пользователь системы: ученик или администратор (п.6 ТЗ — users).

    Наследуется от AbstractBaseUser, поэтому Django использует это модель
    как AUTH_USER_MODEL: session, login/logout, password hash — из коробки.
    Поля `password` и `last_login` унаследованы (hasher + DateTimeField).
    """

    class Role(models.TextChoices):
        STUDENT = "student", "Ученик"
        ADMIN = "admin", "Администратор"

    username = models.CharField("Логин", max_length=150, unique=True)
    # password и last_login наследуются от AbstractBaseUser (hasher, не plaintext)
    full_name = models.CharField("ФИО", max_length=200)
    email = models.EmailField("Электронная почта", unique=True)
    grade = models.CharField("Класс", max_length=20, blank=True)
    role = models.CharField(
        "Роль", max_length=20, choices=Role.choices, default=Role.STUDENT
    )
    is_active = models.BooleanField("Активен", default=True)
    is_blocked = models.BooleanField(
        "Заблокирован",
        default=False,
        help_text="Заблокированный пользователь не может войти (этап 2).",
    )
    email_confirmed = models.BooleanField("E-mail подтверждён", default=False)
    created_at = models.DateTimeField("Дата регистрации", auto_now_add=True)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["full_name"]

    objects = UserManager()

    class Meta:
        db_table = "users"
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def __str__(self):
        return f"{self.full_name} ({self.username})"

    # --- Интерфейс, ожидаемый Django auth / admin ---------------------
    @property
    def is_staff(self):
        """Флаг для django.contrib.admin — доступ по роли admin."""
        return self.role == self.Role.ADMIN

    def has_perm(self, perm, obj=None):
        return self.is_active and not self.is_blocked and self.role == self.Role.ADMIN

    def has_module_perms(self, app_label):
        return self.has_perm("")

    # --- Проверка пароля без изменения модели -------------------------
    def verify_password(self, raw_password):
        """Проверяет пароль по хешу (для кастомного authenticate backend)."""
        if not self.password or not raw_password:
            return False
        return check_password(raw_password, self.password)

    def set_password(self, raw_password):
        """Хеширует пароль перед сохранением (override AbstractBaseUser)."""
        self.password = make_password(raw_password)


class Category(models.Model):
    """Категория книг (п.6 ТЗ — categories)."""

    name = models.CharField("Название", max_length=100, unique=True)
    description = models.TextField("Описание", blank=True)

    class Meta:
        db_table = "categories"
        verbose_name = "Категория"
        verbose_name_plural = "Категории"

    def __str__(self):
        return self.name


class Book(models.Model):
    """Книга в каталоге школьной библиотеки (п.6 ТЗ — books)."""

    class Condition(models.TextChoices):
        NEW = "new", "Новая"
        GOOD = "good", "Хорошая"
        FAIR = "fair", "Потрёпанная"

    title = models.CharField("Название", max_length=200)
    author = models.CharField("Автор", max_length=200)
    catalog_number = models.CharField(
        "Каталожный номер", max_length=30, unique=True, blank=True,
        help_text="Формируется автоматически: ШК-ГГГГ-NNNN.",
    )
    year = models.PositiveIntegerField("Год издания", null=True, blank=True)
    category = models.ForeignKey(
        Category,
        verbose_name="Категория",
        on_delete=models.PROTECT,
        related_name="books",
    )
    cover = models.ImageField("Обложка", upload_to="covers/", blank=True, null=True)
    description = models.TextField("Краткое описание", blank=True)
    condition = models.CharField(
        "Состояние", max_length=10, choices=Condition.choices, default=Condition.GOOD
    )
    owner = models.ForeignKey(
        User,
        verbose_name="Владелец",
        on_delete=models.CASCADE,
        related_name="books",
    )
    is_available = models.BooleanField("Доступна для обмена", default=True)
    created_at = models.DateTimeField("Дата добавления", auto_now_add=True)

    class Meta:
        db_table = "books"
        verbose_name = "Книга"
        verbose_name_plural = "Книги"

    def __str__(self):
        return f"{self.title} — {self.author}"

    def save(self, *args, **kwargs):
        """Автоматически присваивает каталожный номер при первом сохранении.

        Номер формируется ДО вставки (по максимальному текущему pk+1), чтобы
        не делать повторный UPDATE с update_fields — иначе Django падает с
        «Update fields are not allowed: created_at» из-за auto_now_add.
        """
        if not self.catalog_number:
            from django.db.models import Max
            next_pk = (Book.objects.aggregate(m=Max("pk"))["m"] or 0) + 1
            year = timezone.now().year
            self.catalog_number = f"ШК-{year}-{next_pk:04d}"
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("catalog:book_detail", args=[self.pk])


class Ad(models.Model):
    """Объявление об обмене книги (п.6 ТЗ — ads; этап 4 — доска объявлений)."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Активно"
        ARCHIVED = "archived", "В архиве"
        CLOSED = "closed", "Закрыто"

    class Type(models.TextChoices):
        GIVE = "give", "Отдам"
        SEEK = "seek", "Ищу"
        EXCHANGE = "exchange", "Обменяю"

    book = models.ForeignKey(
        Book,
        verbose_name="Книга",
        on_delete=models.SET_NULL,
        related_name="ads",
        null=True,
        blank=True,
        help_text="Необязательно: объявление может быть без привязки к каталогу.",
    )
    author = models.ForeignKey(
        User,
        verbose_name="Автор объявления",
        on_delete=models.CASCADE,
        related_name="ads",
    )
    title = models.CharField("Название", max_length=200)
    ad_type = models.CharField(
        "Тип", max_length=10, choices=Type.choices, default=Type.EXCHANGE
    )
    text = models.TextField("Описание", blank=True)
    contact = models.CharField(
        "Контакт", max_length=200, blank=True,
        help_text="По умолчанию подставляется из профиля (e-mail).",
    )
    photos = models.JSONField(
        "Фотографии", default=list, blank=True,
        help_text="До 3 относительных путей в MEDIA (ads_photos/...).",
    )
    status = models.CharField(
        "Статус", max_length=10, choices=Status.choices, default=Status.ACTIVE
    )
    created_at = models.DateTimeField("Дата публикации", auto_now_add=True)

    class Meta:
        db_table = "ads"
        verbose_name = "Объявление"
        verbose_name_plural = "Объявления"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
