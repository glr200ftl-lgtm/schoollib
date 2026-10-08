# Школьная библиотека (schoollib)

Сайт школьной библиотеки: онлайн-каталог книг + доска объявлений для обмена
книгами между учениками.

**Стек (зафиксирован):** Python 3.12 + Django 5.x + PostgreSQL 16
(для локальной разработки допустим SQLite). Шаблоны Django + собственный CSS.

## Структура

```
manage.py            — точка входа Django
schoollib/           — настройки, корневые URL
catalog/             — приложение каталога: модели users/categories/books/ads,
                       страницы / и /catalog, команда seed_demo
exchange/            — приложение раздела обмена: страница /exchange
templates/           — base.html (шапка/футер) и страницы
static/css/style.css — стили layout
media/covers/        — обложки-заглушки (генерируются сидом)
```

## Установка и запуск

### Вариант 1: PostgreSQL (основной)

Требуется PostgreSQL 16 с созданной базой, либо docker:

```bash
docker run -d --name schoollib-pg -e POSTGRES_DB=schoollib \
  -e POSTGRES_USER=schoollib -e POSTGRES_PASSWORD=schoollib -p 5432:5432 postgres:16

python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py seed_demo
python manage.py runserver                            # http://127.0.0.1:8000/
```

Параметры подключения задаются переменными окружения (значения по умолчанию
совпадают с командой docker выше): `POSTGRES_DB`, `POSTGRES_USER`,
`POSTGRES_PASSWORD`, `POSTGRES_HOST` (localhost), `POSTGRES_PORT` (5432).

### Вариант 2: SQLite (быстрая локальная проверка)

```bash
pip install -r requirements.txt
DATABASE_URL=sqlite python manage.py migrate
DATABASE_URL=sqlite python manage.py seed_demo
DATABASE_URL=sqlite python manage.py runserver
```

## Демо-данные (seed)

`python manage.py seed_demo` — идемпотентен, повторный запуск не создаёт
дубликаты. Создаёт:

| Что | Сколько | Детали |
|---|---|---|
| Пользователи | 3 | `admin` / `admin123` (библиотекарь), `student1`, `student2` / `student123` |
| Категории | 6 | Учебники, Художественная литература, Научно-популярное, Детская литература, Справочники и словари, Подготовка к экзаменам |
| Книги | 12 | С обложками-заглушками (Pillow, PNG в `media/covers/`) |
| Объявления | 3 | Доска обмена |

## Страницы этапа 1

- `/` — главная (счётчики книг/категорий)
- `/catalog/` — каталог (список seed-книг с обложками)
- `/exchange/` — заглушка «раздел в разработке»

Поиск, авторизация, формы подачи объявлений — следующие этапы (см. STAGES.md).

## Проверка

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/          # 200
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/catalog/  # 200
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/exchange/ # 200
```
