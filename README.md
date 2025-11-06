# eRAP Bot with NCALayer Dialog Automation for Linux
## Полноценный бот для автоматизации работы с порталом eRAP с автоматическим вводом пароля в диалог NCALayer


Использует:
- Playwright для веб-автоматизации
- xdotool для ввода пароля в NCALayer (основной метод)
- pynput как запасной вариант

Установка зависимостей:
    pip install playwright pynput pydantic-settings
    playwright install chromium
    sudo apt-get install xdotool  # для Linux

Настройка:
    Создайте файл .env:
    CERT_PASSWORD=ваш_пароль_от_сертификата
    BASE_URL=https://erap-public.kgp.kz/#/login

Запуск:
uvicorn main:app --reload --host 0.0.0.0 --port 8000

Playwright → Клик "Войти с ЭЦП" → xdotool вводит пароль → Успешный вход

Требует: xdotool (Linux)
Установка: sudo apt-get install xdotool