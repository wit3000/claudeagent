# Triple-Pass Text Reviewer

Публичный сервис: пользователь заходит по ссылке, вставляет текст, получает результаты трёх независимых LLM-проверок и может поделиться отчётом.

- **Pass 1 — Technical Proofreader:** факты / логика / стиль.
- **Pass 2 — Nitpicking Logic Editor:** только логика и противоречия.
- **Pass 3 — First-Time Reader:** свежий взгляд, читательские сбои.

Три прогона идут параллельно, изолированно, `temperature=0`. Каждый обязан цитировать текст дословно — цитаты, которых нет в исходнике, автоматически отбраковываются как галлюцинации и не попадают в консенсус.

## Как этим делиться

1. Задеплой сервис (см. ниже).
2. Отправь пользователю корневую ссылку — они увидят форму.
3. После проверки каждый отчёт получает постоянный URL вида `https://ваш-домен/r/<job_id>` и кнопку **Copy share link** — этой ссылкой можно делиться, отчёт лежит в SQLite и переживает рестарт.

## Деплой на Render.com (~3 минуты)

1. Форкни репозиторий или зайди в свой (файл `render.yaml` уже в корне).
2. На [render.com](https://render.com) → **New** → **Blueprint** → выбери репо.
3. Render прочитает `render.yaml` и создаст веб-сервис + постоянный диск.
4. В настройках сервиса → **Environment** → введи `ANTHROPIC_API_KEY`.
5. Deploy. Через ~2 минуты получишь публичный URL: `https://triple-pass-reviewer.onrender.com`.

По умолчанию `PUBLIC_MODE=1` — любой с ссылкой может отправить текст. Защита: rate-limit **20 проверок/час на IP** и **20 000 символов на текст** (правится через env `RATE_LIMIT_PER_HOUR`, `MAX_TEXT_CHARS`).

Если хочешь закрыть паролем: убери `PUBLIC_MODE`, добавь `APP_PASSWORD=...` — при заходе браузер спросит логин (любой) и этот пароль.

## Деплой на Fly.io / Railway / любой VPS

Есть `Dockerfile` — работает где угодно. Обязательные env:
`ANTHROPIC_API_KEY`, `MODEL_ID` (по умолчанию `claude-sonnet-5`), `PUBLIC_MODE=1` **или** `APP_PASSWORD`. Опциональные: `RATE_LIMIT_PER_HOUR`, `MAX_TEXT_CHARS`, `DB_PATH` (должен быть на персистентном диске).

## Локальный запуск

```bash
cp .env.example .env
# вписать ANTHROPIC_API_KEY
pip install -e .[dev]
uvicorn reviewer.web.app:app --reload --port 8080
open http://localhost:8080
```

## Docker

```bash
docker compose up --build
```

## CLI

```bash
python -m reviewer review path/to/text.txt --id my-text-01
# отчёт: out/my-text-01.md и .json
```

## Тесты

```bash
pytest
```

## Гарантии выполнения

- `temperature=0`, версии промтов зафиксированы (`PASS_VERSION`).
- Три вызова изолированы: никаких общих сообщений, порядок рандомизирован.
- JSON-контракт + один автоматический retry, если модель нарушила формат.
- Верификация цитат: дословное совпадение с исходником (нормализация кавычек и пробелов).
- Кросс-проверка категорий и диапазона абзацев на стороне парсера.
- Если у прогона >30% галлюцинаций — он помечается `unreliable` в отчёте.
- Rate-limit и лимит длины текста — на стороне сервера, не полагаемся на клиента.

## Структура

```
src/reviewer/
  passes.py         # системные промты трёх прогонов (константы, версии)
  preprocess.py     # нумерация абзацев/предложений
  parser.py         # разбор JSON + верификация цитат
  consensus.py      # сведение по правилу 2-из-3 / 1-из-3
  orchestrator.py   # параллельный запуск трёх вызовов
  llm.py            # Anthropic SDK с ретраями
  report.py         # рендер Markdown
  cli.py            # typer CLI
  web/app.py        # FastAPI (JSON API + HTML + shareable /r/<id>)
  web/db.py         # SQLite (SQLModel), персистентная история
  web/jobs.py       # фоновой запуск проверок
  web/auth.py       # PUBLIC_MODE или HTTP Basic
  web/ratelimit.py  # per-IP rate limit + лимит длины
  static/           # одна страница на Alpine.js
```
