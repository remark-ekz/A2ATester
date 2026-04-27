# A2A Tester

A2A Tester - локальное приложение для тестирования A2A-агентов через удобный GUI.

Приложение позволяет создавать подключения к агентам, настраивать headers, TLS-сертификаты, metadata JSON, запускать новые диалоги с отдельным `contextId`, отправлять `message/send` и `message/stream`, видеть чат, статусы задач, артефакты и полный JSON-лог запросов/ответов.

## Что внутри

- Python backend на FastAPI.
- Статический frontend на HTML/CSS/JavaScript без Node/Vite.
- Desktop-окно через `pywebview`.
- SQLite-база для профилей, чатов, сообщений, артефактов и HTTP diagnostics.
- Сборка в один исполняемый файл через PyInstaller.

Подробное описание архитектуры, базы, request lifecycle, TLS, diagnostics и порядка отображения A2A-событий находится в [docs/PROJECT_DOCUMENTATION.md](docs/PROJECT_DOCUMENTATION.md).

## Возможности

- Профили подключений к разным A2A-хостам.
- Сохранение endpoint, headers, TLS-настроек, путей к сертификатам, metadata и timeout.
- Header Manager:
  - добавление, редактирование и удаление headers;
  - включение/отключение header;
  - маскирование секретных значений.
- Выбор файлов сертификатов через file picker.
- Новый чат создает новый `contextId`.
- Чаты сохраняются в SQLite и доступны в левом списке.
- Поддержка:
  - `message/send`;
  - `message/stream`;
  - `tasks/get`;
  - `tasks/cancel`;
  - загрузки Agent Card из `/.well-known/agent-card.json`.
- Поддержка `input-required`: следующий ответ в том же чате отправляется с тем же `contextId` и текущим `taskId`.
- Отображение в чате:
  - сообщений пользователя;
  - сообщений агента;
  - task status;
  - artifacts;
  - ошибок.
- Прокручиваемая JSON diagnostics-панель.
- Выбор цветовой палитры с сохранением.

## Установка для разработки

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

## Запуск

Обычный запуск desktop-приложения:

```bash
python -m a2a_tester.main
```

Portable-режим, где база и данные лежат рядом с приложением в `./data`:

```bash
python -m a2a_tester.main --portable
```

Запуск только как локального web-сервера без desktop-окна:

```bash
python -m a2a_tester.main --host 127.0.0.1 --port 7860 --no-browser
```

Проверка инициализации без запуска сервера:

```bash
python -m a2a_tester.main --portable --smoke-test
```

## Сборка

Сборка одного исполняемого файла:

```bash
python scripts/build.py
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
python scripts/build.py --app
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

Сами выбранные сертификаты копируются в `data/certificates/`.

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
```

## Замечания

- Raw diagnostics маскирует чувствительные response headers.
- Значения request headers хранятся в профиле, поэтому для production-секретов лучше использовать отдельные тестовые токены.
- Если порт занят, приложение автоматически попробует следующий свободный порт.
- На macOS one-file бинарник может требовать запуск вне sandbox из-за ограничений системных semaphore.
