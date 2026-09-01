# Triple-Pass Text Reviewer

Один агент прогоняет присланный текст через три независимых LLM-проверки:

- **Pass 1 — Technical Proofreader:** факты / логика / стиль.
- **Pass 2 — Nitpicking Logic Editor:** только логика и противоречия.
- **Pass 3 — First-Time Reader:** свежий взгляд, читательские сбои.

Все три прогона идут параллельно, в изолированных вызовах, `temperature=0`. Каждый обязан цитировать текст дословно; цитаты, которых нет в исходнике, помечаются как галлюцинации и не попадают в консенсус.

## Правила интерпретации (встроены в код)

- Дефект подтверждён 2–3 прогонами → **high**, править сразу.
- Дефект найден 1 прогоном → **low**, точечно проверить.
- Категория, в которой у ответственных прогонов 0 findings, → **clean**.
- Больше трёх прогонов не делается.

## Запуск локально

```bash
cp .env.example .env
# заполнить ANTHROPIC_API_KEY и APP_PASSWORD
pip install -e .[dev]
uvicorn reviewer.web.app:app --reload --port 8080
# открыть http://localhost:8080
```

Логин через HTTP Basic: любой username, пароль — `APP_PASSWORD`.

## CLI

```bash
python -m reviewer review path/to/text.txt --id my-text-01
# отчёт: out/my-text-01.md и out/my-text-01.json
```

## Docker

```bash
docker compose up --build
```

## Тесты

```bash
pytest
```

## Гарантии выполнения

- `temperature=0`, версии промтов зафиксированы (`PASS_VERSION`).
- Три вызова изолированы: никаких общих сообщений, порядок рандомизирован.
- JSON-контракт + один автоматический retry, если модель нарушила формат.
- Верификация цитат: дословное совпадение с исходником (после нормализации кавычек и пробелов).
- Кросс-проверка категорий и диапазона абзацев на стороне парсера.
- Если у прогона >30% галлюцинаций — он помечается `unreliable` в отчёте.

## Структура

```
src/reviewer/
  passes.py         # системные промты трёх прогонов (константы, версии)
  preprocess.py     # нумерация абзацев/предложений
  parser.py         # разбор JSON-ответа + верификация цитат
  consensus.py      # сведение по правилу 2-из-3 / 1-из-3
  orchestrator.py   # параллельный запуск трёх вызовов
  llm.py            # Anthropic SDK с ретраями
  report.py         # рендер Markdown
  cli.py            # typer CLI
  web/app.py        # FastAPI (JSON API + HTML)
  static/           # одна страница на Alpine.js
```
