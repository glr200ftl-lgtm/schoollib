"""Формы доски объявлений (Этап 4).

Создание/редактирование объявления: название, книга(автор книги), тип,
описание, до 3 фото (валидация типа/размера), контакт (по умолчанию из
профиля), статус.
"""

from django import forms

from catalog.models import Ad, Book

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_PHOTO_SIZE = 3 * 1024 * 1024  # 3 МБ на файл
MAX_PHOTOS = 3


class AdForm(forms.ModelForm):
    """Форма объявления; поле «Автор» — книга и её автор (по ТЗ п.3.3.1)."""

    photo1 = forms.FileField(label="Фото 1", required=False)
    photo2 = forms.FileField(label="Фото 2", required=False)
    photo3 = forms.FileField(label="Фото 3", required=False)

    class Meta:
        model = Ad
        fields = ["title", "book", "ad_type", "text", "contact", "status"]
        widgets = {
            "text": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        # видимость книг в выпадающем списке — все из каталога (seed)
        self.fields["book"].required = False
        self.fields["book"].queryset = Book.objects.order_by("title")
        # статус доступен только админу (ученик не выставляет статусы сам);
        # этапы модерации — этап 7
        if self.user is not None and self.user.role != "admin":
            del self.fields["status"]
        if not self.initial.get("contact") and self.user is not None:
            self.initial["contact"] = self.user.email

    def clean_photo1(self):
        return self._clean_photo("photo1")

    def clean_photo2(self):
        return self._clean_photo("photo2")

    def clean_photo3(self):
        return self._clean_photo("photo3")

    def clean_contact(self):
        contact = self.cleaned_data["contact"].strip()
        if not contact:
            # по умолчанию — из профиля
            if self.user is not None:
                return self.user.email or self.user.username
            raise forms.ValidationError("Укажите контакт для связи.")
        return contact

    def _clean_photo(self, name: str):
        f = self.cleaned_data.get(name)
        if not f:
            return None
        content_type = getattr(f, "content_type", "")
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise forms.ValidationError(
                f"Файл «{f.name}»: допустимы только изображения JPG/PNG/WEBP/GIF."
            )
        if f.size > MAX_PHOTO_SIZE:
            raise forms.ValidationError(
                f"Файл «{f.name}»: размер не должен превышать 3 МБ."
            )
        return f

    def get_photos(self):
        """Возвращает список загруженных новых файлов (валидация уже в clean_*)."""
        return [f for f in (self.cleaned_data.get(n) for n in
                            ("photo1", "photo2", "photo3")) if f]


class AdDeletePhotosForm(forms.Form):
    """Отметки «удалить это фото» при редактировании."""

    remove_photo_0 = forms.BooleanField(required=False)
    remove_photo_1 = forms.BooleanField(required=False)
    remove_photo_2 = forms.BooleanField(required=False)

    def kept(self, existing):
        keep = []
        for i, path in enumerate(existing[:MAX_PHOTOS]):
            if not self.cleaned_data.get(f"remove_photo_{i}"):
                keep.append(path)
        return keep
