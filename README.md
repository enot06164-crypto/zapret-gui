# Zapret GUI

Web-интерфейс для управления [zapret](https://github.com/Flowseal/zapret-discord-youtube) — обход DPI.

![Dashboard](screenshots/dashboard.png)

## Возможности

- Автоскачивание и обновление zapret с GitHub
- Запуск/остановка стратегий (bat-файлов)
- Установка/удаление службы Windows
- Редактирование списков (list-general, list-exclude, ipset)
- Настройки: Game Filter, IPSet, Auto-Update
- Диагностика системы
- Просмотр результатов тестов

## Скриншоты

### Dashboard
![Dashboard](screenshots/dashboard.png)

### Strategy
![Strategy](screenshots/strategy.png)

### Service
![Service](screenshots/service.png)

### Settings
![Settings](screenshots/settings.png)

### Lists
![Lists](screenshots/lists.png)

### Diagnostics
![Diagnostics](screenshots/diagnostics.png)

### Tests
![Tests](screenshots/tests.png)

## Запуск

### Через .exe (рекомендуется)

Скачайте `ZapretGUI.exe` и запустите двойным кликом.

### Через Python

```bash
pip install -r requirements.txt
python zapret_gui.py
```

Или через `start.bat`.

## Требования

- Windows 10/11
- Python 3.10+ (для запуска через Python)
- Microsoft Edge WebView2 Runtime (для .exe, обычно уже установлен)
