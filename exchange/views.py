"""Доска объявлений (Этап 4).

/exchange — лента активных объявлений незаблокированных пользователей,
фильтры «Отдам / Ищу / Обменяю», поиск по названию.
/exchange/{id} — карточка объявления.
/exchange/new, /exchange/{id}/edit, /exchange/{id}/delete,
/exchange/{id}/archive — создание/редактирование/удаление/архивация своих
объявлений (чужие -> 403).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import connections
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from catalog.models import Ad, User

PER_PAGE = 12


def _search_filter(query: str):
    """Поиск по названию объявления: частичное совпадение, регистронезависимо.

    На SQLite LOWER()/icontains фолдит только ASCII (кириллица не работает),
    поэтому для малых объёмов школьной доски фильтруем на уровне Python;
    на PostgreSQL используем обычный icontains.
    """
    q = query.strip().lower()
    if not q:
        return None
    if connections["default"].vendor == "sqlite":
        ids = [a.pk for a in Ad.objects.filter(title__isnull=False)
               if q in a.title.lower()]
        return Q(pk__in=ids)
    return Q(title__icontains=q)


def _visible_to_guest():
    """Активные объявления незаблокированных авторов."""
    return Ad.objects.filter(
        status=Ad.Status.ACTIVE,
        author__is_blocked=False,
    ).select_related("author", "book")


def exchange_list(request):
    ads = _visible_to_guest()

    ad_type = request.GET.get("type", "")
    if ad_type in dict(Ad.Type.choices):
        ads = ads.filter(ad_type=ad_type)

    q = request.GET.get("q", "").strip()
    search_q = _search_filter(q) if q else None
    if search_q is not None:
        ads = ads.filter(search_q)

    # счётчики типов считаются по той же выборке без фильтра по типу
    base_for_counts = _visible_to_guest()
    if search_q is not None:
        base_for_counts = base_for_counts.filter(search_q)
    counts = {
        t: base_for_counts.filter(ad_type=t).count() for t, _ in Ad.Type.choices
    }

    paginator = Paginator(ads.order_by("-created_at"), PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "exchange/exchange.html",
        {
            "page_obj": page_obj,
            "total_count": paginator.count,
            "types": Ad.Type.choices,
            "counts": counts,
            "current_type": ad_type,
            "q": q,
            "can_create": request.user.is_authenticated
            and request.user.role == User.Role.STUDENT
            and not request.user.is_blocked,
        },
    )


def ad_detail(request, pk):
    ad = get_object_or_404(Ad.objects.select_related("author", "book"), pk=pk)
    hidden = (
        ad.status != Ad.Status.ACTIVE or ad.author.is_blocked
    ) and ad.author_id != getattr(request.user, "id", None)
    if hidden:
        return redirect("exchange:list")
    return render(request, "exchange/ad_detail.html", {"ad": ad})


def _save_photos(new_files):
    from django.conf import settings

    saved_paths = []
    for f in new_files:
        dest_dir = settings.MEDIA_ROOT / "ads_photos"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f.name
        with open(dest, "wb") as out:
            for chunk in f.chunks():
                out.write(chunk)
        saved_paths.append(f"ads_photos/{f.name}")
    return saved_paths


@login_required
def ad_create(request):
    from exchange.forms import AdForm

    if request.method == "POST":
        form = AdForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            ad = form.save(commit=False)
            ad.author = request.user
            if not ad.contact:
                ad.contact = request.user.email or request.user.username
            ad.status = Ad.Status.ACTIVE
            ad.save()
            new_files = form.get_photos()
            if new_files:
                ad.photos = _save_photos(new_files)
                ad.save(update_fields=["photos"])
            messages.success(request, "Объявление опубликовано.")
            return redirect("exchange:detail", pk=ad.pk)
    else:
        form = AdForm(user=request.user, initial={"contact": request.user.email})
    return render(
        request, "exchange/ad_form.html", {"form": form, "mode": "Создание"}
    )


def _check_owner(request, ad):
    if ad.author_id != request.user.id and request.user.role != User.Role.ADMIN:
        return HttpResponseForbidden(
            "Редактировать и удалять можно только свои объявления."
        )
    return None


@login_required
def ad_edit(request, pk):
    from exchange.forms import AdForm

    ad = get_object_or_404(Ad, pk=pk)
    denied = _check_owner(request, ad)
    if denied:
        return denied

    if request.method == "POST":
        form = AdForm(request.POST, request.FILES, instance=ad, user=request.user)
        if form.is_valid():
            kept = list(ad.photos)
            remove_indexes = [
                i for i in range(3)
                if request.POST.get(f"remove_photo_{i}")
            ]
            kept = [p for i, p in enumerate(kept) if i not in remove_indexes]
            new_files = form.get_photos()
            if len(kept) + len(new_files) > 3:
                form.add_error(None, "Можно прикрепить не более 3 фотографий.")
            else:
                updated = form.save()
                added = _save_photos(new_files)
                if added or remove_indexes:
                    updated.photos = kept + added
                    updated.save(update_fields=["photos"])
                messages.success(request, "Объявление обновлено.")
                return redirect("exchange:detail", pk=updated.pk)
    else:
        form = AdForm(instance=ad, user=request.user)
    return render(
        request,
        "exchange/ad_form.html",
        {"form": form, "mode": "Редактирование", "ad": ad},
    )


@login_required
def ad_delete(request, pk):
    ad = get_object_or_404(Ad, pk=pk)
    denied = _check_owner(request, ad)
    if denied:
        return denied
    if request.method == "POST":
        ad.delete()
        messages.success(request, "Объявление удалено.")
        return redirect("accounts:my")
    return render(request, "exchange/ad_confirm_delete.html", {"ad": ad})


@login_required
def ad_archive(request, pk):
    """Архивация/возврат своего объявления (ученик)."""
    ad = get_object_or_404(Ad, pk=pk)
    denied = _check_owner(request, ad)
    if denied:
        return denied
    if request.method == "POST":
        if ad.status == Ad.Status.ACTIVE:
            ad.status = Ad.Status.ARCHIVED
            messages.success(
                request, "Объявление убрано в архив (не видно в общей ленте)."
            )
        elif ad.status == Ad.Status.ARCHIVED:
            ad.status = Ad.Status.ACTIVE
            messages.success(request, "Объявление возвращено в ленту.")
        ad.save(update_fields=["status"])
    return redirect("accounts:my")
