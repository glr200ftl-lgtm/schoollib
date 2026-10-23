@echo off
title SchoolLib
call .venv\Scripts\activate.bat
set DATABASE_URL=sqlite
echo.
echo ==========================================
echo   SchoolLib is running!
echo   Open in browser: http://127.0.0.1:8000/
echo ==========================================
echo.
python manage.py runserver
pause
