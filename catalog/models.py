from django.db import models


class User(models.Model):
    """Пользователь системы: ученик или администратор (п.6 ТЗ — users)."""

    class Role(models.TextChoices):
        STUDENT = "student", "Ученик"
        ADMIN = "admin", "Администратор"

    username = models.CharField("Логин", max_length=150, unique=True)
    # Пароль будет задействован на этапе авторизации; сейчас храним хеш заготовки.
    password = models.CharField("Пароль (хеш)", max_length=128, blank=True)
    full_name = models.CharField("ФИО", max_length=200)
    email = models.EmailField("Электронная почта", blank=True)
    grade = models.CharField("Класс", max_length=20, blank=True)
    role = models.CharField(
        "Роль", max_length=20, choices=Role.choices, default=Role.STUDENT
    )
    is_active = models.BooleanField("Активен", default=True)
    created_at = models.DateTimeField("Дата регистрации", auto_now_add=True)

    class Meta:
        db_table = "users"
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def __str__(self):
        return f"{self.full_name} ({self.username})"


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


class Ad(models.Model):
    """Объявление об обмене книги (п.6 ТЗ — ads)."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Активно"
        CLOSED = "closed", "Закрыто"

    book = models.ForeignKey(
        Book,
        verbose_name="Книга",
        on_delete=models.CASCADE,
        related_name="ads",
    )
    author = models.ForeignKey(
        User,
        verbose_name="Автор объявления",
        on_delete=models.CASCADE,
        related_name="ads",
    )
    title = models.CharField("Заголовок", max_length=200)
    text = models.TextField("Текст объявления")
    status = models.CharField(
        "Статус", max_length=10, choices=Status.choices, default=Status.ACTIVE
    )
    created_at = models.DateTimeField("Дата публикации", auto_now_add=True)

    class Meta:
        db_table = "ads"
        verbose_name = "Объявление"
        verbose_name_plural = "Объявления"

    def __str__(self):
        return self.title
