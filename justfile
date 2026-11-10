set shell := ["powershell.exe", "-NoLogo", "-Command"]

# Запуск Telegram-бота
start:
    python -m app.main

# Запуск всех тестов
test:
    python -m pytest

# Проверка кода Ruff
check:
    ruff check .

# Автоматическое исправление ошибок Ruff
check-fix:
    ruff check . --fix

# Полная очистка БД и заполнение тарифов
db-clean:
    python -m test_data.db_flush_all
    python -m test_data.db_fill_plans

# Применение всех неприменённых миграций Alembic
migrate:
    python -m alembic upgrade head