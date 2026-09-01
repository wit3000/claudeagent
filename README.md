---
title: Triple-Pass Text Reviewer
emoji: 🔍
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

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

## Деплой на Hugging Face Spaces (бесплатно, без карты)

1. На [huggingface.co](https://huggingface.co) → **New Space**.
   - Owner: твой аккаунт.
   - Space name: любое (например `triple-pass-reviewer`).
   - License: любая (`mit` подойдёт).
   - **SDK: Docker** → **Blank**.
   - Hardware: `CPU basic` (бесплатный).
   - Visibility: **Private** (чтобы никто чужой не жёг твой API-ключ).
2. Space создан → открой вкладку **Settings** → **Variables and secrets** → **New secret**:
   - Name: `ANTHROPIC_API_KEY` · Value: твой ключ.
   - (опционально) `APP_PASSWORD` — тогда убери `PUBLIC_MODE` (см. ниже). Для приватного Space это не обязательно: доступ уже ограничен твоим HF-аккаунтом.
3. Залей код из этого репозитория в Space. Проще всего через git:
   ```bash
   git clone https://huggingface.co/spaces/<твой-user>/triple-pass-reviewer hf-space
   cd hf-space
   # скопировать содержимое этого репозитория (кроме .git)
   cp -r /path/to/claudeagent/{Dockerfile,pyproject.toml,README.md,src} .
   git add -A && git commit -m "init" && git push
   ```
   Или через UI: **Files** → **Add file** → перетащить `Dockerfile`, `pyproject.toml`, `README.md`, папку `src/`.
4. HF автоматически соберёт Docker-образ (~2 минуты, статус в **Logs**). Готовый URL: `https://<твой-user>-triple-pass-reviewer.hf.space`.

**Важно про приватные Spaces:** ссылка работает только когда ты залогинен на HF. Для тебя одного — идеально.

**Про хранилище:** на бесплатном тарифе постоянного диска нет — при перезапуске Space (например, после сна) SQLite сбрасывается, история проверок теряется. Сами проверки работают нормально. Для персонального теста этого достаточно.

**Про засыпание:** после ~48ч без активности Space засыпает, при заходе просыпается за ~30 секунд. Ключ не тратится.

## Деплой на любой VPS

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
