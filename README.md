# A2A Tester

A2A Tester - локальное приложение для тестирования A2A-агентов через удобный GUI.

Приложение позволяет создавать подключения к агентам, настраивать headers, TLS-сертификаты, metadata JSON, запускать новые диалоги с отдельным `contextId`, отправлять запросы A2A, видеть чат, статусы задач, артефакты и полный JSON-лог запросов/ответов.

## Что внутри

- Python backend на FastAPI.
- Статический frontend на HTML/CSS/JavaScript без Node/Vite.
- Desktop-окно через `pywebview`; если на Linux нет GTK/Qt backend, приложение открывает обычный браузер без шумных traceback от `pywebview`.
- SQLite-база для профилей, чатов, сообщений, артефактов и HTTP diagnostics.
- Сборка в один исполняемый файл через PyInstaller.

Подробное описание архитектуры, базы, request lifecycle, TLS, diagnostics и порядка отображения A2A-событий находится в [docs/PROJECT_DOCUMENTATION.md](docs/PROJECT_DOCUMENTATION.md).

## Возможности

- Профили подключений к разным A2A-хостам.
- Сохранение endpoint, точных ручек запросов, headers, TLS-настроек, путей к сертификатам, metadata и timeout.
- Header Manager в виде строк:
  - добавление через `+`;
  - редактирование ключа и значения прямо в списке;
  - включение/отключение header галочкой;
  - сохранение или удаление отдельной строки маленькими кнопками справа.
- Выбор сертификатов двумя способами: `Pick Path` сохраняет абсолютный путь, `Import Copy` копирует файл в data-dir приложения.
- Новый чат создает новый `contextId` в формате UUIDv7.
- Чаты сохраняются в SQLite и доступны в левом списке.
- Количество чатов в левом списке настраивается для каждого подключения.
- В карточке чата показывается превью первого пользовательского сообщения.
- Чат можно удалить из списка одним нажатием; связанные сообщения, artifacts и diagnostics удаляются вместе с ним.
- Версии A2A JSON-RPC: `0.1`, `0.2`, `0.3` и `1.0`.
- Для `0.1`-`0.3` используются методы `message/send`, `message/stream`, `tasks/get`, `tasks/cancel` и прежний формат `Message`/`Part`.
- Для A2A `1.0` используются `SendMessage`, `SendStreamingMessage`, `GetTask`, `CancelTask`, формат частей без `kind` и новые оболочки ответов `task`, `message`, `statusUpdate`, `artifactUpdate`.
- Во все запросы автоматически добавляется `A2A-Version` выбранной версии; пользовательский заголовок с тем же именем сохраняет приоритет, чтобы можно было проверять негативные сценарии.
- Поле `tenant` для A2A `1.0`: его значение попадёт в `params` каждого вызова, когда агент требует маршрутизацию через `AgentCard.supportedInterfaces`.
- Загрузка Agent Card из `/.well-known/agent-card.json`.
- Для каждой операции можно указать отдельную ручку. Если поле пустое, JSON-RPC методы уходят на основной endpoint, Agent Card - на `/.well-known/agent-card.json` от host.
- Поддержка `input-required`: следующий ответ в том же чате отправляется с тем же `contextId` и текущим `taskId`.
- Конструктор сообщения из нескольких частей в произвольном порядке: текст, структурированные данные JSON и файлы.
- Отправка файлов до 8 МБ прямо в JSON-RPC запросе: для A2A `0.1`-`0.3` через `file.bytes`, для A2A `1.0` через `raw`.
- Просмотр входящих DataPart/частей `data` как раскрываемого JSON, копирование JSON, скачивание файлов из `base64` и чтение файлов по URL. Для ссылки на хост агента используются TLS и headers подключения; во внешнюю ссылку учётные данные не передаются.
- Отображение в чате:
  - сообщений пользователя;
  - сообщений агента;
  - task status;
  - artifacts;
  - ошибок.
- Прокручиваемая JSON diagnostics-панель.
- Выбор цветовой палитры с сохранением.
- Анимация ожидания ответа и счетчик секунд во время запроса.

## Установка для разработки

Для запуска и сборки используется `uv`. Скрипты ниже создают окружение вне каталога проекта: на macOS это `~/Library/Caches/A2ATester/venv`. Это важно, если рабочая папка находится в `Documents`, iCloud Drive или другой медленной синхронизируемой директории.

```bash
brew install uv
python3 scripts/run_dev.py --smoke-test
```

## Запуск

Обычный запуск desktop-приложения:

```bash
python3 scripts/run_dev.py
```

На Linux для настоящего desktop-окна нужен GTK (`PyGObject/gi`) или Qt (`qtpy` + `PyQt6`/`PySide6`). Если GUI-backend не установлен, приложение поднимет локальный сервер и откроет системный браузер. Это нормальный fallback, само приложение при этом работает.

Portable-режим, где база и данные лежат рядом с приложением в `./data`:

```bash
python3 scripts/run_dev.py --portable
```

Запуск только как локального web-сервера без desktop-окна:

```bash
python3 scripts/run_dev.py --host 127.0.0.1 --port 7860 --no-browser
```

Проверка инициализации без запуска сервера:

```bash
python3 scripts/run_dev.py --portable --smoke-test
```

## Сборка

Сборка одного исполняемого файла:

```bash
python3 scripts/build.py
```

Результат появится здесь:

```text
dist/A2ATester
```

Запуск собранного приложения:

```bash
./dist/A2ATester --portable
```

Запуск собранного приложения только как локального сервера:

```bash
./dist/A2ATester --portable --no-browser --port 7860
```

На macOS также можно собрать `.app` bundle:

```bash
python3 scripts/build.py --app
```

Но для пересылки проще использовать обычный single-file бинарник из `dist/A2ATester`.

## Где хранятся данные

В обычном режиме приложение использует системную папку данных пользователя.

В portable-режиме:

```text
data/
  a2a_tester.sqlite3
  certificates/
```

SQLite хранит:

- профили подключений;
- чаты;
- сообщения;
- артефакты;
- HTTP diagnostics;
- выбранную тему.

Если сертификат выбран через `Pick Path`, в базе хранится абсолютный путь к исходному файлу. Если выбран `Import Copy`, файл копируется в `data/certificates/`, а в базе хранится путь к этой копии. В обычной браузерной вкладке браузер не отдает приложению настоящий абсолютный путь к локальному файлу, поэтому там для file picker доступен именно режим импорта копии.

## Очистка локальных данных

Если после изменения схемы или разработки нужно полностью сбросить локальные данные, сначала посмотрите, что будет удалено:

```bash
python scripts/reset_data.py
```

Удалить portable-данные рядом с проектом и системную app-data папку:

```bash
python scripts/reset_data.py --yes
```

Только portable-режим:

```bash
python scripts/reset_data.py --portable --yes
```

Только системная папка приложения:

```bash
python scripts/reset_data.py --system --yes
```

Если база лежит в нестандартном месте:

```bash
python scripts/reset_data.py --path /path/to/a2a_tester.sqlite3 --yes
python scripts/reset_data.py --scan ~/some-folder
```

Без `--yes` скрипт работает в dry-run режиме и ничего не удаляет.

## Структура проекта

```text
a2a_tester/
  main.py              # точка входа
  server.py            # FastAPI backend, API, desktop shell
  frontend/
    index.html         # UI
    app.css            # стили
    app.js             # логика frontend
  a2a/
    client.py          # HTTP/SSE transport
    jsonrpc.py         # JSON-RPC payload builders
    render.py          # извлечение messages/status/artifacts
    sse.py             # SSE parser
  storage/
    database.py        # SQLite schema и repository-методы
    paths.py           # пути к app data
scripts/
  build.py             # PyInstaller build
  run_dev.py           # запуск через uv во внешнем virtual environment
  uv_environment.py    # расположение virtual environment для скриптов
  reset_data.py        # поиск и очистка локальной SQLite/data
```

## Замечания

- Raw diagnostics маскирует чувствительные response headers.
- Значения request headers хранятся в профиле, поэтому для production-секретов лучше использовать отдельные тестовые токены.
- Если порт занят, приложение автоматически попробует следующий свободный порт.
- На macOS one-file бинарник может требовать запуск вне sandbox из-за ограничений системных semaphore.
