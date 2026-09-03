---
title: Triple-Pass Text Reviewer
emoji: 🔍
colorFrom: blue
colorTo: gray
sdk: gradio
sdk_version: "5.9.1"
app_file: app.py
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
3. После каждой проверки в интерфейсе появляется прямая ссылка вида
   `https://ваш-домен/?job=<id>` — по ней открывается именно этот отчёт.
   Отчёты хранятся в SQLite (на бесплатном HF диск эфемерный — история
   сбрасывается при перезапуске Space; сами проверки работают всегда).

## Выбор LLM-провайдера

Провайдер выбирается переменной `LLM_PROVIDER` без правки кода:
`groq` (по умолчанию, бесплатный, без карты) · `openai` · `anthropic` ·
`gemini` · `openrouter`. Ключ читается из переменной провайдера
(`GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`,
`OPENROUTER_API_KEY`). Модель — через `MODEL_ID` (у каждого провайдера свой
дефолт).

Опциональный автопереход при сбое — `LLM_FALLBACK_CHAIN` (список
`провайдер:модель` через запятую). Если первый упал, берётся следующий, и в
отчёте появляется пометка. Полный список переменных — в `.env.example`.

## Деплой на Hugging Face Spaces (Gradio SDK, бесплатно, без карты)

**Создать Space один раз:**

1. На [huggingface.co](https://huggingface.co) → **New Space**.
   - **SDK: Gradio** → **Blank**. Hardware: `CPU basic` (или `ZeroGPU` —
     GPU не используется). Visibility: **Private**.
2. **Settings → Variables and secrets → New secret**: `GROQ_API_KEY` =
   твой ключ ([console.groq.com/keys](https://console.groq.com/keys),
   без карты). При другом провайдере — соответствующая переменная.

**Заливка кода — одной командой** (больше не нужно копипастить файлы):

```bash
pip install huggingface_hub
export HF_TOKEN=hf_...   # write-токен из huggingface.co/settings/tokens
python scripts/deploy_hf.py --space <твой-hf-user>/triple-pass-reviewer
```

Скрипт заливает `app.py`, `requirements.txt`, `README.md` и `src/`,
игнорируя тесты, кэши и локальные данные. После пуша HF сам пересоберёт
Space (~1–2 минуты, статус в **Logs**). Повторный деплой — та же команда.

## Деплой на любой VPS

Есть `Dockerfile`. Обязательные env: `LLM_PROVIDER` + ключ провайдера.
Опциональные: `MODEL_ID`, `LLM_FALLBACK_CHAIN`, `MAX_TEXT_CHARS`,
`PROCESS_MAX_PER_HOUR`, `DB_PATH` (на персистентном диске).

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
