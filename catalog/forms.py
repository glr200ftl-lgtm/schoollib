"""Формы административного управления каталогом (Этап 5).

- AdminBookForm: все поля книги + загрузка обложки с валидацией типа/размера;
- CategoryForm: создание/переименование категории.
"""

from django import forms

from catalog.models import Book, Category

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_COVER_SIZE = 5 * 1024 * 1024  # 5 МБ


class AdminBookForm(forms.ModelForm):
    """Книга: добавление/редактирование администратором."""

    # Обложка — отдельное FileField (без встроенной проверки ImageField,
    # которая отклоняет файл раньше нашей валидации и не переводится);
    # тип/размер проверяются в clean_cover. required=False у модели —
    # при редактировании пустое поле оставляет существующую обложку.
    cover = forms.FileField(label="Обложка", required=False)

    class Meta:
        model = Book
        fields = [
            "title", "author", "catalog_number", "year", "category",
            "description", "condition", "is_available",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }
        help_texts = {
            "catalog_number": "Оставьте пустым — присвоится автоматически (ШК-ГГГГ-NNNN).",
        }

    def clean_cover(self):
        cover = self.files.get("cover")
        if not cover:
            # файл не загружен — не трогаем существующую обложку
            return None
        content_type = getattr(cover, "content_type", "") or ""
        allowed_exts = ("jpg", "jpeg", "png", "webp", "gif")
        ext = cover.name.rsplit(".", 1)[-1].lower() if "." in cover.name else ""
        if content_type not in ALLOWED_IMAGE_TYPES and ext not in allowed_exts:
            raise forms.ValidationError(
                "Обложка: можно загрузить только изображение (JPG, PNG, WEBP или GIF)."
            )
        if cover.size > MAX_COVER_SIZE:
            raise forms.ValidationError(
                "Обложка: размер файла не должен превышать 5 МБ."
            )
        try:
            from PIL import Image
            Image.open(cover).verify()
            cover.seek(0)
        except Exception:
            raise forms.ValidationError(
                "Обложка: можно загрузить только изображение (JPG, PNG, WEBP или GIF)."
            )
        return cover

    def save(self, commit=True):
        book = super().save(commit=False)
        cover = self.cleaned_data.get("cover")
        if cover:
            book.cover = cover
        if commit:
            book.save()
        return book

    def clean_catalog_number(self):
        """Понятная ошибка при дубликате каталожного номера."""
        number = (self.cleaned_data.get("catalog_number") or "").strip()
        qs = Book.objects.filter(catalog_number__iexact=number)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if number and qs.exists():
            dup = qs.first()
            raise forms.ValidationError(
                f"Каталожный номер «{number}» уже занят книгой «{dup.title}». "
                "Укажите уникальный номер или оставьте поле пустым для автоприсвоения."
            )
        return number


class CategoryForm(forms.ModelForm):
    """Категория: создание/переименование."""

    class Meta:
        model = Category
        fields = ["name", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }
