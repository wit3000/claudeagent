# ТЗ: Photograde — Custom GPT для параметрической обработки фото «в стилистике X»

Статус: **версия 3.** Платформа — приватный Custom GPT пользователя; RAW,
Lightroom-пресеты (XMP) и LUT не нужны. Непроверенные факты о платформе
помечены «не проверено» — по ним заложены консервативные допущения.

## 0. Контекст

### 0.1. Что хочет пользователь

Пользователь присылает своему GPT фото и просит обработать его «в
стилистике» (например, цветокоррекция как в Twin Peaks или Supernatural).
GPT сам редактирует фото «как в Lightroom» — теми же по смыслу ползунками —
и отдаёт:

1. обработанный файл;
2. сравнение «до/после»;
3. текстовый отчёт «какие ползунки и насколько подвинуты».

Дальше пользователь просит правки обычными словами («тени чуть темнее»,
«меньше зерна»), а GPT меняет один-два параметра и перерисовывает
результат. Lightroom пользователь не использует, поэтому переносимость во
внешние программы (XMP, LUT) не нужна.

### 0.2. Ключевые архитектурные решения (обязательны к прочтению)

1. **Платформа — приватный Custom GPT** (у пользователя платная подписка
   с созданием GPT). Пользователь собирает GPT в конструкторе: вставляет
   текст в поле Instructions, загружает файлы в Knowledge, включает Code
   Interpreter и веб-поиск. Движок — Python-модуль, который GPT импортирует
   в песочнице Code Interpreter и запускает над загруженным фото.
2. **Обработка детерминированная и параметрическая, не генеративная.**
   Модель (vision + рассуждение) выбирает параметры `ParamSet` (JSON),
   движок применяет их кодом. gpt-image не используется: генеративное
   редактирование перерисовывает кадр (дрейф лиц и деталей, ограничение
   разрешения, потеря EXIF).
3. **Движок работает только на numpy + Pillow + стандартной библиотеке.**
   OpenCV, если импортируется, — необязательное ускорение с фолбэком на
   numpy. scipy, pydantic и прочее не используются: в песочнице нет
   интернета и `pip install`, состав предустановленных библиотек официально
   не задокументирован.
4. **Параметры — язык ползунков Lightroom** (имена, смысл, диапазоны),
   потому что он знаком пользователю. Совместимость с самим Lightroom и
   численное совпадение с его рендером — **не цель**.
5. **Итеративный цикл — ядро продукта.** GPT держит текущий ParamSet в
   диалоге (и дублирует в файл в песочнице), на каждую просьбу меняет
   только нужные поля, перерисовывает и показывает отчёт об изменениях.
6. **Референсы.** GPT может искать описания стиля веб-поиском ChatGPT, но
   скачать картинки в песочницу не может (там нет сети). Источники стиля:
   (а) встроенная библиотека луков `looks.json` (параметры и описание
   палитры, никаких кадров); (б) референс-кадр, присланный пользователем
   в чат → `match_reference`; (в) текстовое описание из веб-поиска →
   параметры по словарю из `reference.md`. GPT не обещает скопировать чужие
   кадры.

### 0.3. Что известно о платформе

| Факт | Значение | Статус |
|---|---|---|
| Подписка с созданием GPT | есть у пользователя | подтверждено пользователем |
| Видимость GPT | приватный, «Only me» | решение пользователя |
| Лимит поля Instructions | 8000 символов | подтверждено отчётами на форуме OpenAI; официальную справку прочитать не удалось |
| Лимит Knowledge | до 20 файлов, ≤ 512 МБ на файл | источники расходятся (10 или 20 файлов); используем 3 |
| Код в песочнице | Python 3.13.5, NumPy 2.3.5, Pillow 12.1.1, opencv-python-headless 4.13, SciPy 1.17 (снимок на март 2026) | неофициальный gist; состав может меняться → OpenCV/scipy не обязательны |
| Сеть в песочнице | исходящих запросов нет | подтверждено несколькими источниками |
| Время на один вызов кода | исторически ~60 с | не проверено → проектируем под ≤ 45 с на вызов |
| Память песочницы | не опубликована | не проверено → бюджет ≤ 1.5 ГБ пиковой памяти |
| Жизнь песочницы | сбрасывается после простоя (по неофициальным данным — часы) | не проверено → источник истины для ParamSet — диалог, а не файл |
| Файлы Knowledge доступны в `/mnt/data` | обычно да | не проверено официально; известны случаи, когда GPT переписывает код вместо импорта → правило и фолбэк в 2.11.1 |

### 0.4. Допущения

- **A1.** Платформа MVP — приватный Custom GPT (Instructions + Knowledge +
  Code Interpreter + веб-поиск).
- **A2.** Форматы: JPEG, PNG, TIFF. 8 бит — всегда; 16-битный RGB — только
  при наличии OpenCV в песочнице (иначе понятная ошибка, 2.6). RAW, HEIC,
  WebP не поддерживаются.
- **A3.** Выход: обработанный JPEG (или PNG/TIFF по просьбе) +
  JPEG «до/после» + текстовый отчёт об изменённых ползунках + JSON с
  ParamSet.
- **A4.** Рабочий размер: превью ≤ 1024 px, результат по умолчанию ≤ 4096 px
  по длинной стороне; полный размер — по явной просьбе (`max_side=None`).
- **A5.** Размещение в репозитории: `plugins/photograde/`; в папке `gpt/`
  лежит ровно то, что пользователь загружает в конструктор.
- **A6.** Приёмку «в живом GPT» выполняет пользователь (у Лупы нет доступа к
  ChatGPT); Лупа отвечает за локальные тесты и чек-лист.

Открытых вопросов к пользователю нет.

## 1. Что уже работает (не ломать)

- Репозиторий содержит сервис `reviewer`: `src/reviewer/**`, `app.py`,
  `tests/*.py`, корневой `pyproject.toml` (`testpaths = ["tests"]`),
  `requirements.txt`, `Dockerfile`, `scripts/deploy_hf.py`, `landing/`.
- **Запрещено** менять файлы вне `plugins/photograde/`, кроме одной строки
  в корневом `README.md` (2.14). Корневые `pyproject.toml`,
  `requirements.txt`, `Dockerfile`, `.gitignore` не трогать.
- Корневой `pytest -q` остаётся зелёным и не собирает тесты плагина.
- `scripts/deploy_hf.py` не должен начать заливать `plugins/` (он заливает
  только `app.py`, `requirements.txt`, `README.md`, `src/` — так и остаётся).

## 2. Задача

### 2.1. Структура и поставка

```
plugins/photograde/
  gpt/                        # РОВНО то, что загружается в конструктор GPT
    photograde.py             # движок: один модуль, numpy + Pillow (+ cv2 опционально)
    looks.json                # библиотека луков (2.10)
    reference.md              # Knowledge: справочник для GPT (2.11.2)
    instructions.md           # текст для поля Instructions (≤ 7500 символов, 2.11.1)
  GUIDE_RU.md                 # гайд «как собрать свой GPT» (2.13)
  README.md                   # для разработчика: структура, тесты, сборка
  pyproject.toml              # только для локальной разработки/тестов
  .gitignore                  # dist/
  scripts/
    regen_golden.py           # перегенерация golden-эталонов
    build_bundle.py           # dist/photograde-gpt.zip = gpt/* + GUIDE_RU.md
  tests/
    conftest.py               # sys.path -> gpt/, синтетические изображения (6.1)
    golden/cases.json
    golden/*.npz
    test_spec.py test_color.py test_io.py test_stages.py test_geometry.py
    test_masks.py test_analyze_match.py test_looks.py test_report.py
    test_api.py test_backends.py test_gpt_texts.py test_golden.py test_perf.py
```

**Почему один модуль, а не zip-пакет:** Knowledge гарантированно принимает
текстовые файлы; приём `.zip` и сохранность его имени не проверены. Один
`.py` импортируется двумя строками, и тестируется ровно тот файл, который
поставляется. Объём модуля ориентировочно 2500–3200 строк; модуль разбит на
секции с заголовками-комментариями в порядке разделов этого ТЗ.

Требования к `photograde.py`:

- Совместимость: Python ≥ 3.10 (в песочнице 3.13), numpy ≥ 1.24 и 2.x,
  Pillow ≥ 9.5. Только стандартная библиотека + numpy + Pillow; `cv2`
  импортируется в `try/except ImportError` (2.3.4).
- При импорте — никаких вычислений, вывода в stdout, записи файлов.
- `__version__ = "0.1.0"`; `ENGINE_INFO()` →
  `{"version", "numpy", "pillow", "cv2": str | None, "backend": "cv2" | "numpy"}`.
- Все публичные функции имеют docstring на английском с примером вызова
  (GPT читает их через `help()`).
- Исключения: `PhotogradeError(Exception)` и наследники `ParamError`,
  `UnsupportedFormatError`, `CorruptImageError`, `ImageTooLargeError`,
  `GeometryError`, `LookNotFoundError`. Сообщения — на английском, с путём к
  полю и подсказкой (например
  `"light.exposur: unknown key. Did you mean 'exposure'?"` — через
  `difflib.get_close_matches`).

`pyproject.toml` (локальная разработка): `[project] name = "photograde"`,
`version = "0.1.0"`, `requires-python = ">=3.10"`,
`dependencies = ["numpy>=1.24", "Pillow>=9.5"]`,
`optional-dependencies: accel = ["opencv-python-headless>=4.8"], dev = ["pytest>=8.0", "ruff>=0.6"]`;
`[tool.setuptools] py-modules = ["photograde"]`, `package-dir = {"" = "gpt"}`;
`[tool.pytest.ini_options] testpaths = ["tests"]`, маркер `slow`,
`addopts = "-m 'not slow'"`; ruff: line-length 100, select E, F, I.

`scripts/build_bundle.py`: собирает `dist/photograde-gpt.zip` из
`gpt/photograde.py`, `gpt/looks.json`, `gpt/reference.md`,
`gpt/instructions.md`, `GUIDE_RU.md`; перед сборкой проверяет длину
`instructions.md` (≤ 7500 символов) и импортируемость модуля; печатает
список файлов и их размеры.

### 2.2. Схема параметров (`ParamSet`)

ParamSet — обычный `dict` (JSON). Валидация — собственная, без pydantic:
таблица `PARAM_SPEC` в модуле описывает для каждого поля тип, диапазон,
дефолт, русскую и английскую подпись (для отчёта, 2.7.3). Из неё же
генерируются дефолты, клампинг, сообщения об ошибках и JSON Schema
(`schema()`).

Нотация: `int[-100..100]=0` — целое, диапазон, дефолт; `float` — шаг 0.01.
Все поля имеют нейтральный дефолт, допускается частичный ParamSet.

```
version: 1
white_balance:
  temp:  int[-100..100]=0      # относительный сдвиг: + теплее, - холоднее
  tint:  int[-100..100]=0      # + маджента, - зелёный
light:
  exposure:   float[-5.0..5.0]=0.0   # EV
  contrast, highlights, shadows, whites, blacks: int[-100..100]=0
presence:
  texture, clarity, dehaze, vibrance, saturation: int[-100..100]=0
tone_curve:                     # точки [x, y], int 0..255, 2..16 точек
  master, red, green, blue: list[[int,int]] = [[0,0],[255,255]]
hsl:                            # Color: red, orange, yellow, green, aqua, blue, purple, magenta
  hue, saturation, luminance: {Color: int[-100..100]}   # отсутствующий ключ = 0
color_grading:
  shadows, midtones, highlights, global: {hue: int[0..359]=0, sat: int[0..100]=0, lum: int[-100..100]=0}
  blending: int[0..100]=50
  balance:  int[-100..100]=0
detail:
  sharpening:      {amount: int[0..150]=0, radius: float[0.5..3.0]=1.0, detail: int[0..100]=25, masking: int[0..100]=0}
  noise_reduction: {luminance: int[0..100]=0, luminance_detail: int[0..100]=50,
                    luminance_contrast: int[0..100]=0, color: int[0..100]=0,
                    color_detail: int[0..100]=50, color_smoothness: int[0..100]=50}
lens:
  distortion:          int[-100..100]=0   # + исправляет бочку
  vignetting:          int[-100..100]=0   # + осветляет углы (коррекция объектива)
  vignetting_midpoint: int[0..100]=50
  chromatic_aberration: {remove: bool=False, red_cyan: int[-100..100]=0, blue_yellow: int[-100..100]=0}
transform:
  upright:    "off"|"level"|"vertical" = "off"
  vertical, horizontal, aspect: int[-100..100]=0
  rotate:     float[-10.0..10.0]=0.0     # градусы
  scale:      int[50..150]=100
  offset_x, offset_y: float[-100..100]=0.0
  constrain:  bool=True
crop: null | {left, top, right, bottom: float[0..1], angle: float[-45..45]=0}   # left<right, top<bottom
effects:
  vignette: {amount: int[-100..100]=0, midpoint: int[0..100]=50, roundness: int[-100..100]=0,
             feather: int[0..100]=50, highlights: int[0..100]=0,
             style: "highlight_priority"|"color_priority"|"paint_overlay" = "highlight_priority"}
  grain:    {amount: int[0..100]=0, size: int[0..100]=25, roughness: int[0..100]=50, seed: int>=0 = 0}
local: list[LocalAdjustment] = []   # ≤ 16, раздел 2.8
```

`normalize(params: dict | None) -> tuple[dict, list[str]]`:

- Возвращает **полный** ParamSet (все поля заполнены) и предупреждения.
- Неизвестный ключ, неверный тип, неизвестный цвет HSL, неизвестный
  `style`/`upright`/`type` маски → `ParamError` с путём к полю и подсказкой.
- Строковые числа (`"15"`) принимаются с предупреждением; bool в числовом
  поле — ошибка.
- Числа вне диапазона клампятся, предупреждение
  `"light.exposure: 7.0 -> 5.0 (clamped)"`; дробное в int-поле округляется
  без предупреждения.
- Кривые: сортировка по x; дубликаты x, < 2 или > 16 точек → ошибка;
  координаты вне 0..255 клампятся с предупреждением.
- `crop.left >= right` или `top >= bottom` → ошибка; `local` > 16 → ошибка.
- Идемпотентность: `normalize(normalize(p)[0]) == (normalize(p)[0], [])`.

`schema() -> dict` — JSON Schema (draft 2020-12) из `PARAM_SPEC`.
`describe_params(lang="ru") -> str` — компактная таблица полей (путь,
подпись, тип, диапазон, дефолт, одна строка смысла).
`compact(params) -> dict` — только поля, отличные от нейтральных (для
показа в диалоге и хранения).

### 2.3. Цвет, ресемплинг, бэкенды

#### 2.3.1. Цветовая модель

- Рабочее пространство: **линейный RGB (праймериз sRGB/Rec.709), float32,
  ≥ 0, без верхнего клампа** до кодирования результата.
- Перцептивное = sRGB OETF (IEC 61966-2-1; для > 1 — продолжение степенной
  ветки); EOTF — обратная.
- Luma: `0.2126 R + 0.7152 G + 0.0722 B`; `Y` — на линейных, `l` — на
  перцептивных значениях.
- RGB↔HSV (hue в градусах [0,360)) и linear sRGB↔CIE Lab (D65) —
  векторизованно на numpy.

#### 2.3.2. Примитивы (numpy-реализация обязательна)

- `_gaussian(img, sigma)`: sigma < 0.3 → без изменений; sigma ≤ 4 —
  сепарабельная свёртка ядром радиуса `ceil(3*sigma)` (сумма сдвинутых
  срезов, паддинг reflect); sigma > 4 — три прохода box-blur через
  кумулятивные суммы с ширинами по формуле аппроксимации Гаусса тремя
  box-фильтрами (Kovesi). Вход 2D или 3D (по каналам).
- `_box(img, r)` — box-фильтр через кумулятивные суммы, паддинг reflect.
- `_guided_filter(I, p, r, eps)` — guided filter (He et al.) на `_box`.
- `_min_filter(img2d, k)` — сепарабельный минимум
  (`np.lib.stride_tricks.sliding_window_view` по каждой оси).
- `_sample_bilinear(channel, map_x, map_y, fill=0.0)` — билинейная выборка
  по картам координат, вне кадра → `fill`.
- `_resize(img, (w, h), kind)` — по каналам через Pillow mode `"F"`:
  уменьшение — `Image.Resampling.BOX`, увеличение — `BILINEAR` или
  `BICUBIC` (аргумент).
- `_kmeans(samples, k, iters, seed)` — k-means++ init с
  `np.random.default_rng(seed)`, `iters` итераций Ллойда.
- `_sobel_mag(l)` — модуль градиента Собеля (свёртка срезами).

#### 2.3.3. Порог размера и память

- `MAX_INPUT_MP = 100` (проверка по размеру из заголовка Pillow до
  декодирования) → иначе `ImageTooLargeError`. `Image.MAX_IMAGE_PIXELS`
  выставляется в `MAX_INPUT_MP*1e6` на время открытия и восстанавливается.
- При `max_side=4096` (~11 Мп) пиковое потребление ≤ 1.5 ГБ:
  промежуточные буферы освобождать (`del`), float32 везде, без float64
  массивов полного размера.

#### 2.3.4. Бэкенды

- `_BACKEND = "cv2"`, если `import cv2` успешен и не задана переменная
  окружения `PHOTOGRADE_BACKEND=numpy`; иначе `"numpy"`.
- `cv2` используется только для: `_gaussian` (`cv2.GaussianBlur`), `_box`
  (`cv2.blur`), `_min_filter` (`cv2.erode`), `_sample_bilinear`
  (`cv2.remap`, `INTER_LINEAR`), `_resize` (`INTER_AREA` /
  `INTER_LINEAR` / `INTER_CUBIC`), чтение/запись 16-бит (2.6). Остальная
  логика одна.
- Эталон — numpy-бэкенд (golden генерируются на нём). Расхождение бэкендов
  на полном рендере: средняя абсолютная разница ≤ 0.003, максимальная
  ≤ 0.03 (тест, если cv2 установлен локально).

### 2.4. Пайплайн

`_render(img_linear, P, *, scale, original_long_edge) -> (image, warnings, applied_upright)`
— внутренняя функция; публичный вход — `apply()` (2.7).

`scale` = длинная сторона обрабатываемого / длинная сторона оригинала. Все
пиксельные радиусы (NR, тон, шарпинг, clarity, texture, dehaze, зерно)
заданы для оригинала и умножаются на `scale`, чтобы превью и результат
выглядели одинаково.

Порядок стадий фиксирован; стадия с нейтральными параметрами пропускается
без вычислений:

| # | Стадия | Пространство |
|---|--------|--------------|
| 1 | Шумоподавление | перцептивное |
| 2 | Геометрия: дисторсия + ХА + transform + crop (одна выборка); коррекция виньетирования объектива | линейное |
| 3 | Баланс белого | линейное |
| 4 | Экспозиция | линейное |
| 5 | Whites/Blacks (глобально) → Highlights/Shadows (локально-адаптивно) → Contrast (глобально) | перцептивная luma |
| 6 | Dehaze → Clarity → Texture | перцептивное |
| 7 | Tone Curve: master, затем R/G/B | перцептивное |
| 8 | HSL / Color Mixer | перцептивное (HSV) |
| 9 | Color Grading | перцептивное |
| 10 | Vibrance, Saturation | перцептивное |
| 11 | Локальные коррекции | по параметру |
| 12 | Шарпинг | перцептивная luma |
| 13 | Виньетка (post-crop) | см. 2.4.13 |
| 14 | Зерно | перцептивное |

**Почему порядок отличается от «WB → тон → кривая → HSL → детали → оптика →
эффекты → маски»:** NR — до тональных операций (иначе поднятые тени
усиливают шум); геометрия — раньше всего, чтобы виньетка и зерно ложились
на финальный кадр, а маски задавались в его координатах; локальные
коррекции — до шарпинга и эффектов (как в LR).

Между стадиями изображение передаётся в линейном пространстве; стадия сама
конвертирует. Оптимизация «конвертировать на границах групп» допустима,
если golden-тесты не меняются.

Обозначения: `x` — перцептивное значение, `s(t) = sin(πt)²`, `smoothstep`
с клампингом, `clamp01`, `G(img, σ)` = `_gaussian`.

#### 2.4.1. Шумоподавление

- Luminance (`L = luminance/100 > 0`): перцептивный RGB → Y, Cb, Cr
  (BT.601 full range). К Y:
  `Y_den = _guided_filter(Y, Y, r=max(1, round((1 + 4*L)*scale)), eps=(0.02 + 0.10*L)**2)`;
  `Y' = lerp(Y_den, Y, 0.5*luminance_detail/100)`;
  `Y' += (luminance_contrast/100) * 0.25 * (Y - G(Y, 2*scale))`.
- Color (`color > 0`), `σ = (color/100)*8*scale`: для Cb, Cr
  `b = G(c, σ)`; при `color_smoothness > 0` —
  `b = lerp(b, G(c, 2σ), color_smoothness/100*0.5)`;
  `c' = lerp(b, c, 0.5*color_detail/100)`.

#### 2.4.2. Геометрия

Обратное отображение: для каждого пикселя выхода вычисляется точка
источника; выборка `_sample_bilinear` по каждому каналу (R и B — со своими
картами из-за ХА), фон 0; результат клампится снизу к 0. Alpha (если есть)
проходит ту же выборку по карте G.

1. Нормированные координаты: центр (0,0), половина диагонали = 1.
2. Crop: выход = прямоугольник crop (в пикселях), координаты переводятся в
   некадрированный кадр (масштаб/смещение, поворот на `crop.angle` вокруг
   центра прямоугольника).
3. Transform: `p = H⁻¹·p`, `H` — композиция (в порядке применения к
   изображению): vertical, horizontal, rotate, aspect, scale, offset.
   Гомографии 3×3 считаются в numpy (система 8×8 через `np.linalg.solve`
   по 4 парам углов).
   - vertical `v`: верхняя кромка растягивается по ширине относительно
     центра с множителем `k = 1 + 0.4*v/100`, нижняя без изменений.
   - horizontal `h`: правая кромка по высоте, `k = 1 + 0.4*h/100`.
   - rotate: на `rotate` градусов против часовой вокруг центра.
   - aspect `a`: `sx = 1 + a/200`, `sy = 1 - a/200`.
   - scale: `sx, sy *= scale/100`.
   - offset: сдвиг на `offset_x/100*W/2`, `offset_y/100*H/2`.
   - `constrain=True`: бинарный поиск (20 итераций, множитель 1.0..3.0)
     доп. масштаба, при котором 4 угла и 4 середины кромок выхода после
     обратного отображения (с дисторсией) лежат внутри источника; не хватает
     ×3.0 → `GeometryError("transform too strong")`.
4. Дисторсия: `r_s = r*(1 + k1*r²)`, `k1 = -0.25*distortion/100`.
5. ХА: радиус R умножается на `mR = 1 + 0.02*red_cyan/100`, B — на
   `mB = 1 + 0.02*blue_yellow/100`. При `remove=True` ручные значения
   игнорируются, `mR`, `mB` подбираются перебором в [0.995, 1.005] шагом
   0.001 по максимуму корреляции модуля градиента канала с модулем
   градиента G в кольце r ∈ [0.6, 1.0] на копии ≤ 1024 px.
6. Перевод в пиксельные координаты источника.

Коррекция виньетирования объектива (после выборки, линейно):
`img *= 1 + (vignetting/100)*smoothstep(0.8*vignetting_midpoint/100, 1.0, r)`.

#### 2.4.3. Авто-горизонт и вертикали (`detect_upright`)

Без Hough (numpy-only), по ориентациям градиентов:

- Копия ≤ 1024 px, перцептивная luma, `G(·, 1)`, градиенты Собеля `gx, gy`,
  модуль `m`; пиксели с `m` выше 90-го перцентиля — «краевые». Ориентация
  края `α = atan2(gy, gx) + 90°`, приведённая к (-90°, 90°].
- `level`: края с |α| < 20° (почти горизонтальные). Если их суммарный вес
  `Σm` < 0.5% от `Σm` всех краевых — берутся почти вертикальные
  (|α ∓ 90°| < 20°) и их отклонение от вертикали.
  `rotate = -weighted_median(α, m)`, клампинг ±10°.
- `vertical`: сначала поправка `level`. Для почти вертикальных краёв
  (отклонение δ, |δ| < 25°) взвешенным МНК оценивается наклон `c`
  зависимости `δ` от нормированной x-координаты. Затем перебор
  `v ∈ [-100..100]` шагом 2: через гомографию vertical(v) прогоняются 9
  синтетических вертикальных отрезков (x = -0.8..0.8, на всю высоту), по
  ним считается наклон `c(v)`; выбирается `v` с минимальным `|c(v) + c|`.
- `confidence = min(1, Σm_использованных / (0.02 * Σm_всех_пикселей))`;
  если использованных краевых пикселей < 200 → `confidence = 0`, значения 0,
  предупреждение `"upright: not enough edges"`.
- В пайплайне при `transform.upright != "off"` вызов делается по входу до
  геометрии; найденное **прибавляется** к ручным `rotate`/`vertical`
  (с клампингом) и возвращается в `applied_upright`.

#### 2.4.4. Баланс белого

`gR = 2^(0.35*temp/100)`, `gB = 2^(-0.35*temp/100)`, `gG = 2^(-0.35*tint/100)`;
`g /= (0.2126*gR + 0.7152*gG + 0.0722*gB)`; `rgb *= g` (линейно).

#### 2.4.5. Экспозиция и тон

- `rgb *= 2^exposure`.
- На `x = OETF(Y)` последовательно:
  1. whites (глобально): `x += 0.2*(whites/100)*min(x,1)^4`;
  2. blacks (глобально): `x += 0.2*(blacks/100)*(1 - min(x,1))^4`;
  3. highlights/shadows (**локально-адаптивно**, если хотя бы один ≠ 0):
     - базовый слой яркости `b` считается на копии `x`, уменьшенной так,
       чтобы длинная сторона была `min(1024, текущая)`:
       `b_small = _guided_filter(x_s, x_s, r = max(2, round(0.02*long_edge_small)), eps = 0.01)`,
       затем `b = _resize(b_small, full, BILINEAR)`; дальше `b = clamp01(b)`;
     - веса считаются по базе, а не по пикселю:
       `t_h = clamp01((b - 0.5)/0.5)`, `t_s = clamp01(b/0.5)`;
     - `x += 0.12*(highlights/100)*s(t_h) + 0.12*(shadows/100)*s(t_s)`;
     - так светлые/тёмные **области** сдвигаются целиком и локальный
       контраст внутри них сохраняется (как в LR). Guided filter сохраняет
       края, поэтому ореолы на границах «небо/здание» ограничены (тест 6.2
       п.5);
  4. contrast (глобально): для x ∈ [0,1] `x -= 0.5*(contrast/100)*sin(2πx)/(2π)`;
  5. `x' = max(x, 0)`.
- Применение: `rgb *= EOTF(x') / max(Y, 1e-6)`.
- **Почему так.** Раньше Highlights/Shadows были поточечными ради
  переносимости в LUT. LUT больше нет, а локально-адаптивный вариант —
  это то, чего пользователь ждёт от этих ползунков «как в Lightroom».
  Это реально по силам: guided filter на копии ≤ 1024 px — это несколько
  box-фильтров по ~1 Мп (порядка 0.1–0.3 с на numpy) плюс одно билинейное
  увеличение, укладываемся в бюджет 2.5. Whites/Blacks и Contrast остаются
  глобальными: в LR они ведут себя в основном как кривая, и поточечная
  форма гарантирует монотонность.

#### 2.4.6. Dehaze, Clarity, Texture

Перцептивное пространство.

- Dehaze `d = dehaze/100`:
  - `d > 0`: dark channel = min по каналам на копии, уменьшенной в 4 раза,
    → `_min_filter` с нечётным `k = max(3, round(15*scale/4))`; `A` (RGB) —
    среднее входа по пикселям верхних 0.1% dark channel;
    `t = 1 - 0.95*dark/max(A)`, `t = _box(t, max(1, round(10*scale/4)))`,
    увеличение до полного размера, `t = max(t, 0.1)`;
    `J = (I - A)/t + A`; `I' = max(lerp(I, J, d), 0)`.
  - `d < 0`: `k = 0.4*|d|`, `a` — средняя `l` по верхнему 1% пикселей;
    `I' = I*(1-k) + a*k`.
- Clarity: `detail = l - G(l, 0.008*original_long_edge*scale)`;
  `rgb += 0.8*(clarity/100)*detail*4*l*(1-l)`.
- Texture: `detail` с `σ = 0.002*original_long_edge*scale`;
  `rgb += 0.6*(texture/100)*detail`.

#### 2.4.7. Tone Curve

- Монотонная кубическая интерполяция Fritsch–Carlson (PCHIP), своя
  реализация; табуляция 4096 значений на [0,1]; применение `np.interp` к
  каждому каналу перцептивного RGB, клампированного к [0,1].
- master → R, G, B; затем `red` → R, `green` → G, `blue` → B.
- Тождественная кривая пропускается.

#### 2.4.8. HSL

- Перцептивный RGB (клампинг [0,1]) → HSV.
- Центры полос: red 0, orange 30, yellow 60, green 120, aqua 180, blue 240,
  purple 270, magenta 300. Веса — кусочно-линейная интерполяция между двумя
  соседними центрами по кругу (сумма = 1).
- `H' = (H + Σ w_i*hue_i/100*30) mod 360`;
  `S' = clamp01(S*(1 + Σ w_i*sat_i/100))`;
  `V' = clamp01(V*(1 + Σ w_i*lum_i/100*0.5*S))`.
- HSV → RGB.

#### 2.4.9. Color Grading

- `l_b = clamp01(l + balance/200)` (положительный balance — в сторону светов).
- `p = 3 - 2*blending/100`; `w_s = (1-l_b)^p`, `w_h = l_b^p`,
  `w_m = max(0, 1 - w_s - w_h)`; global: `w = 1`.
- Для зоны: `c = hsv2rgb(hue, 1, 1)`, `tint = c - luma(c)`;
  `rgb += w*(sat/100*0.15*tint + lum/100*0.15)`; затем клампинг снизу к 0.

#### 2.4.10. Vibrance и Saturation

- Vibrance: `k = 1 + (vibrance/100)*(1 - S)*skin`, `skin = 0.5` для
  HSV hue ∈ [10°, 50°], иначе 1; `rgb = l + (rgb - l)*k`.
- Saturation: `rgb = l + (rgb - l)*(1 + saturation/100)` (-100 → R=G=B=l).
- Клампинг снизу к 0.

#### 2.4.11. Локальные коррекции — 2.8.

#### 2.4.12. Шарпинг

- `hp = l - G(l, radius*scale)`; `hp = clamp(hp, -lim, lim)`,
  `lim = 0.05 + 0.25*detail/100`.
- Маска краёв: `e = _sobel_mag(G(l, scale))` / его 99-й перцентиль (0 → e=0);
  `m = smoothstep(t0, t0 + 0.1, e)`, `t0 = 0.3*masking/100`; masking=0 → m=1.
- `rgb += (amount/150)*1.5*hp*m`.

#### 2.4.13. Виньетка и зерно

- Виньетка. Нормировка: эллипс по пропорциям кадра проходит через углы при
  `r = 1`. `roundness`: 0 — эллипс кадра; +100 — круг через углы; -100 —
  супер-эллипс с показателем 4 по пропорциям кадра; промежуточные —
  линейная интерполяция расстояний.
  `m = smoothstep(m0, m0 + (1-m0)*(0.05 + 0.95*feather/100), r)`,
  `m0 = 0.9*midpoint/100`.
  - `highlight_priority` (линейно): `f = 2^(1.5*amount/100*m)`; при
    amount < 0 `f = lerp(f, 1, smoothstep(0.7, 1.0, Y)*highlights/100)`;
    `rgb *= f`.
  - `color_priority` (перцептивно):
    `l' = l + 0.6*amount/100*m*(l if amount<0 else 1-l)`; `rgb *= l'/max(l,1e-6)`.
  - `paint_overlay`: `rgb = lerp(rgb, 0 if amount<0 else 1, 0.8*|amount|/100*m)`.
- Зерно: `rng = np.random.default_rng(seed)`; монохромный `N(0,1)` на сетке
  `(ceil(H/k), ceil(W/k))`, `k = max(1, (1 + 3*size/100)*scale)`, увеличение
  `_resize(..., BICUBIC)` → `n1`; второй октав с `max(1, k/2)` → `n2`;
  `n = (1-r)*n1 + r*n2`, `r = roughness/100`, нормировка std = 1;
  `rgb += n*0.08*amount/100*(0.5 + 2*l*(1-l))`. Детерминированно.

#### 2.4.14. Кодирование

Клампинг [0,1], OETF, `np.rint` в uint8 или uint16.

### 2.5. Производительность

Целевые значения (numpy-бэкенд, локальная машина 4 ядра; скорость песочницы
неизвестна — поэтому запас до лимита 45 с):

- превью 1024 px, лук `twin_peaks`: ≤ 3 с;
- результат 4096 px, лук `twin_peaks` (без масок и геометрии): ≤ 25 с;
- `match_reference`: ≤ 10 с;
- пиковая память при 4096 px: ≤ 1.5 ГБ.

Если цель не достигается — оптимизировать (меньше копий, вычисления на
уменьшенных картах), а не повышать лимиты. Результаты замеров — в описание
PR.

### 2.6. Ввод/вывод

`load(path) -> Photo` (dataclass): `linear` (H,W,3) float32, `alpha`
(H,W) float32 | None, `path`, `format` (`"JPEG"|"PNG"|"TIFF"`),
`bit_depth` (8|16), `size` (w,h), `exif: bytes | None`,
`icc_converted_from: str | None`, `warnings: list[str]`.

- Поддерживаемые форматы: JPEG, PNG, TIFF (по содержимому, не по
  расширению). Прочие (включая RAW, HEIC, WebP) → `UnsupportedFormatError`
  с подсказкой «send JPEG/PNG/TIFF».
- Ориентация EXIF применяется (`ImageOps.exif_transpose`); на выходе
  Orientation = 1.
- ICC: `_is_srgb_profile(icc_bytes)` — описание профиля
  (`ImageCms.getProfileDescription`) содержит `"sRGB"`. 8-битное с не-sRGB
  профилем (например, Display P3 с iPhone) → `ImageCms.profileToProfile` в
  sRGB (intent perceptual) + предупреждение `"converted from <описание> to sRGB"`.
  Если `ImageCms` недоступен — профиль игнорируется с предупреждением.
- Режимы Pillow: `L`, `LA`, `P` → RGB(A); `CMYK` → RGB с предупреждением;
  `I;16*` (16-бит grayscale) → поддерживается Pillow напрямую.
- 16-бит RGB(A) PNG/TIFF: Pillow такие файлы корректно не читает. Если
  `_BACKEND == "cv2"` → `cv2.imread(path, IMREAD_UNCHANGED)`
  (BGR(A) → RGB(A)); иначе
  `UnsupportedFormatError("16-bit RGB requires OpenCV in this environment; please send an 8-bit JPEG/PNG/TIFF")`.
  Признак 16-бит RGB определяется по заголовку до декодирования (PNG —
  bit depth в IHDR, TIFF — тег BitsPerSample).
- Многокадровый TIFF → первый кадр + предупреждение.
- Повреждённый файл → `CorruptImageError`.

`save(image, path, *, quality=95, alpha=None, exif=None, strip_gps=True,
bit_depth=8, warnings=None) -> str`:

- `image` — `Result`, `Photo` или массив linear float32. Для `Result`/`Photo`
  `alpha` и `exif` берутся из объекта, если не переданы явно.
- Формат — по расширению: `.jpg/.jpeg` → JPEG (8 бит, `quality`,
  `subsampling=0`, встроенный sRGB ICC из `ImageCms.createProfile("sRGB")`,
  EXIF сохраняется); `.png` → PNG; `.tif/.tiff` → TIFF (LZW). Иное
  расширение → `ParamError`.
- `warnings` — необязательный список, в который функция дописывает
  предупреждения (функция возвращает только путь).
- `bit_depth=16`: только PNG/TIFF и только при `_BACKEND == "cv2"`
  (`cv2.imwrite`); иначе сохраняется 8 бит, в `warnings` —
  `"16-bit output requires OpenCV; saved as 8-bit"`.
- `strip_gps=True`: из EXIF удаляется GPS IFD (тег 0x8825).
- Alpha прикрепляется для PNG/TIFF; для JPEG отбрасывается, в `warnings` —
  `"alpha dropped for JPEG"`.
- Существующий файл не перезаписывается: суффиксы `-1`, `-2`, …
- Папка создаётся при необходимости.

### 2.7. Публичный Python API

Все функции на верхнем уровне модуля. Аргумент `photo` (и `reference`)
везде принимает `Photo` или путь `str`.

| Функция | Сигнатура | Назначение |
|---|---|---|
| `load` | `load(path) -> Photo` | 2.6 |
| `analyze` | `analyze(photo_or_array) -> dict` | статистика, 2.9.1 |
| `list_looks` | `list_looks(path=None) -> list[dict]` | `[{id, name, aliases, description}]`; `path` по умолчанию — `looks.json` рядом с модулем, затем `/mnt/data/looks.json` |
| `get_look` | `get_look(look_id, path=None) -> dict` | полный лук; нет → `LookNotFoundError` со списком id |
| `find_look` | `find_look(query, path=None) -> dict \| None` | id → name/aliases без регистра → подстрока |
| `normalize` | `normalize(params) -> (dict, list[str])` | 2.2 |
| `compact` | `compact(params) -> dict` | только изменённые поля, 2.2 |
| `compose` | `compose(look=None, amount=1.0, params=None) -> (dict, list[str])` | лук × amount + поверх явные params, 2.7.1 |
| `update` | `update(params, changes, *, relative=False) -> (dict, list[str])` | точечная правка по путям, 2.7.4 |
| `diff` | `diff(old, new) -> list[dict]` | что изменилось между двумя ParamSet, 2.7.3 |
| `changes_report` | `changes_report(params, previous=None, lang="ru") -> str` | текстовый отчёт о ползунках, 2.7.3 |
| `apply` | `apply(photo, params=None, *, look=None, amount=1.0, max_side=4096) -> Result` | рендер; `max_side=None` — полный размер; меньшее изображение не увеличивается |
| `preview` | `preview(photo, params=None, *, look=None, amount=1.0, max_side=1024) -> Result` | то же, быстро |
| `before_after` | `before_after(photo, params=None, *, look=None, amount=1.0, out_path=None, max_side=1024) -> str` | JPEG «до \| после» бок о бок, разделитель 4 px белый |
| `diagnose` | `diagnose(before, after) -> dict` | 2.9.3 |
| `detect_upright` | `detect_upright(photo, mode="level") -> dict` | 2.4.3 |
| `match_reference` | `match_reference(photo, reference, *, strength=0.7, components=None) -> MatchResult` | 2.9.2 |
| `save` | 2.6 | |
| `process` | `process(input_path, params=None, *, look=None, amount=1.0, previous=None, out_dir=None, name=None, formats=("jpeg","before_after","params_json"), max_side=4096, quality=95) -> dict` | всё за один вызов, 2.7.2 |
| `load_params` | `load_params(path) -> dict` | чтение ParamSet из JSON + `normalize` |
| `schema`, `describe_params` | 2.2 | |
| `ENGINE_INFO` | 2.1 | |

`Result` (dataclass): `image` (linear float32), `alpha`, `exif`, `params`
(полный нормализованный ParamSet), `warnings`, `scale`, `size`,
`applied_upright`, `source: Photo`.
`MatchResult` (dataclass): `params`, `diagnostics`, `warnings`.

#### 2.7.1. `compose`

- `look` — id (строка; ищется через `find_look`, не найден →
  `LookNotFoundError`) или dict лука; `None` — без лука.
- `amount` вне [0,1] → клампинг с предупреждением.
- Масштабирование лука на `amount`: числовые поля с нейтралью 0 умножаются
  (int — с округлением); **не** масштабируются: `color_grading.*.hue`,
  `color_grading.blending`, `grain.seed/size/roughness`,
  `vignette.midpoint/roundness/feather/highlights/style`,
  `sharpening.radius/detail/masking`, `noise_reduction.*_detail`,
  `noise_reduction.color_smoothness`, `lens.vignetting_midpoint`, bool и
  строки; `transform.scale` → `round(100 + amount*(v - 100))`; кривые →
  `y = round(x + amount*(y - x))` поточечно.
- Поверх — `params` глубоким слиянием (явные значения побеждают; `local` —
  конкатенация: сначала лука, потом params).
- Результат прогоняется через `normalize`; предупреждения объединяются.

#### 2.7.2. `process`

1. `load(input_path)`.
2. `compose(look, amount, params)`.
3. `apply(..., max_side=max_side)`.
4. По `formats`:
   - `"jpeg"|"png"|"tiff"` → `save` в `out_dir`, имя
     `<name or stem>_v<N>.<ext>`, где `N` — следующий свободный номер версии
     в `out_dir` для этого `stem` (1, 2, 3…), чтобы итерации не затирали
     друг друга;
   - `"before_after"` → `<name or stem>_v<N>_before_after.jpg`;
   - `"params_json"` → `<name or stem>_v<N>_params.json` с `compact(params)`
     и полем `"version": 1`.
5. `out_dir` по умолчанию: `/mnt/data/photograde_out`, если `/mnt/data`
   существует, иначе `./photograde_out`.
6. Возврат:
   ```
   {"files": {fmt: path}, "version": N,
    "params": <compact ParamSet>,
    "changes": diff(previous, params) если previous передан, иначе diff(нейтральный, params),
    "report": changes_report(params, previous),
    "warnings": [...], "size": [w, h], "scale": float,
    "diagnose": diagnose(before, after), "elapsed_s": float}
   ```
7. Неизвестный формат в `formats` → `ParamError` до начала обработки.

#### 2.7.3. Отчёт об изменениях: `diff`, `changes_report`

- `diff(old, new)` — оба аргумента нормализуются; результат — список
  `{"path", "label_ru", "label_en", "old", "new", "delta"}` для каждого
  изменившегося листового поля, в порядке групп пайплайна. Для кривых
  `delta` = `None`, `old/new` — списки точек. Для `local` сравнение по
  `name`: добавлена/удалена/изменена коррекция (одна запись на коррекцию с
  перечнем изменённых params).
- `changes_report(params, previous=None, lang="ru")` — человекочитаемый
  текст:
  - без `previous`: заголовок «Настройки (от исходника):», далее группы
    в порядке пайплайна, в каждой — изменённые ползунки строками
    `«Тени: +20»`, `«Экспозиция: −0.30 EV»`, `«HSL · Насыщенность · Синий: −25»`,
    `«Цветокоррекция · Тени: оттенок 190°, насыщенность 18»`,
    `«Кривая (общая): 5 точек — приподняты чёрные (0→12)»` (для кривой —
    краткое описание: подъём/опускание концов и середины);
  - с `previous`: заголовок «Изменено в этой версии:» и строки
    `«Тени: +20 → +10 (−10)»`; затем строка «Остальное без изменений».
  - Если изменений нет — «Без изменений».
  - Подписи берутся из `PARAM_SPEC` (`label_ru`, `label_en`). Русские
    подписи — привычные названия ползунков: Температура, Оттенок,
    Экспозиция, Контраст, Светлые участки, Тени, Белые, Чёрные, Текстура,
    Чёткость, Устранение дымки, Сочность, Насыщенность, Кривая, HSL (Цветовой
    тон / Насыщенность / Яркость; цвета: Красный, Оранжевый, Жёлтый,
    Зелёный, Голубой, Синий, Фиолетовый, Пурпурный), Цветокоррекция
    (Тени / Средние тона / Светлые / Общая, Смешивание, Баланс), Резкость
    (Количество, Радиус, Детализация, Маскирование), Шумоподавление,
    Оптика (Дисторсия, Виньетирование объектива, Хроматические аберрации),
    Трансформация, Кадрирование, Виньетка, Зерно, Локальные коррекции.
  - Знаки: `+N`, `−N` (U+2212), `0`.

#### 2.7.4. `update`

`update(params, changes, *, relative=False)`:

- `params` — текущий ParamSet (полный или compact); `changes` — dict
  `{"light.shadows": -10, "effects.grain.amount": 10, "hsl.saturation.blue": -20}`
  (точечные пути). Пути проверяются по `PARAM_SPEC` (опечатка → `ParamError`
  с подсказкой).
- `relative=False` — присваивание; `relative=True` — прибавление к текущему
  значению (только числовые поля; для прочих → `ParamError`).
- Можно передать путь к целой ветке (`"tone_curve.master": [[0,10],[255,255]]`,
  `"color_grading.shadows": {"hue": 200, "sat": 15}`) — присваивание ветки
  со слиянием.
- `local` правится через `{"local": [...]}` целиком или
  `{"local.<name>.params.exposure": 0.3}` (адресация коррекции по `name`;
  нет такой → `ParamError`).
- Возврат — нормализованный полный ParamSet и предупреждения (клампинг).

### 2.8. Локальные коррекции

```
LocalAdjustment
  name: str (1..40, уникально в пределах ParamSet)
  mask: {components: list[Component] (1..8), invert: bool=False, opacity: int[0..100]=100}
  params: {exposure: float[-4..4]=0, contrast, highlights, shadows, whites, blacks,
           temp, tint, saturation, texture, clarity, dehaze: int[-100..100]=0}

Component (по "type"), у всех mode: "add"|"subtract"|"intersect" = "add"
  linear_gradient: start [x,y], end [x,y]                       # доли кадра 0..1; start != end
  radial: center [x,y], radius_x, radius_y: float(0..2], angle: float[-180..180]=0,
          feather: int[0..100]=50, inside: bool=True
  luminance_range: low, high: int[0..100] (low<=high), feather: int[0..100]=20
  color_range: hue: int[0..359], hue_width: int[1..180]=30, sat_min: int[0..100]=10, feather: int[0..100]=30
  image: path: str                                              # grayscale-маска
```

Кисти не реализуются: модель, рисующая вслепую по координатам, не даёт
полезного результата. ИИ-маски (`ai_subject`, `ai_sky`, `ai_person`) — фаза
2; в MVP такой `type` → `ParamError` с текстом
«AI masks are not supported in this version».

Построение (координаты финального кадра, x вправо, y вниз; маска float32
[0,1]):

- linear_gradient: `t` — проекция на вектор start→end / его длина;
  `m = 1 - smoothstep(0, 1, t)`.
- radial: эллиптическое расстояние `d` с учётом `angle`;
  `f = max(0.01, feather/100)`; `m = 1 - smoothstep(1-f, 1, d)`;
  `inside=False` → `1 - m`.
- luminance_range: `l*100`; трапеция: 1 на [low, high], линейные склоны
  шириной `feather` (0 — жёсткая граница). По изображению на входе стадии 11.
- color_range: HSV того же изображения; по hue — трапеция с плато
  ±hue_width/2 и склонами `feather/100*hue_width` (по кругу);
  `× smoothstep(sat_min/100, sat_min/100 + 0.1, S)`.
- image: Pillow → `L` → ресайз к кадру (BILINEAR) → /255; нет файла →
  `FileNotFoundError`, не читается → `CorruptImageError`.
- Комбинация по порядку: первый — база; `add` → `max`, `subtract` →
  `m*(1-c)`, `intersect` → `m*c`; затем `invert`, затем `*opacity/100`.

Применение: для каждой коррекции `adj` = копия, прогнанная через стадии WB,
exposure, tone (включая локально-адаптивные highlights/shadows), presence
(dehaze/clarity/texture), saturation с её params (те же функции);
`img = lerp(img, adj, mask)` в линейном пространстве. Нейтральные params →
пропуск.

### 2.9. Анализ, перенос стиля, диагностика

#### 2.9.1. `analyze`

На копии ≤ 512 px:

- `luma_percentiles`: p1, p5, p25, p50, p75, p95, p99 (шкала 0..255, 0.1).
- `clipping`: `{"highlights": доля пикселей с любым каналом ≥ 254/255, "shadows": доля с l ≤ 1/255}`.
- `zones`: `shadows` (L* < 33), `midtones`, `highlights` (L* > 66) →
  `{share, L, a, b}`.
- `mean_chroma`: средний C*.
- `hue_bands`: для 8 полос `{share, mean_saturation}` (пиксели с S > 0.15,
  полоса — ближайший центр).
- `dominant_colors`: `_kmeans` K=5, 10 итераций, seed 0, по ≤ 20000
  пикселям (выборка с seed 0) в Lab → `[{hex, share}]` по убыванию share.
- `cast_estimate`: `{a, b}` по пикселям L* 25..75 и C* < 20 (если < 1% —
  `None`).
- `summary`: одна строка на английском (например,
  `"low-key, warm cast, low saturation, 3% clipped highlights"`) по
  порогам: p50 < 80 → low-key, > 170 → high-key; |cast| > 4 по a или b →
  warm/cool/green/magenta cast; mean_chroma < 12 → low saturation,
  > 35 → high saturation; клиппинг > 1% → упоминание.

#### 2.9.2. `match_reference`

Оба изображения ≤ 512 px (для шага 3 — ≤ 128 px). Шаги по `components`
(по умолчанию все: `wb, tone, color, saturation, hsl`), каждый — на
источнике с уже применёнными параметрами предыдущих шагов.

1. `wb`: перебор `temp, tint` (шаг 20 по [-100..100], затем ±20 вокруг
   лучшего шагом 5); минимум расстояния средних (a*, b*) пикселей
   L* 25..75; итог `round(found*strength)`.
2. `tone`: `m(x) = CDF_ref⁻¹(CDF_src(x))` по гистограммам `l` (256 бинов);
   точки x = 0, 16, 32, 64, 96, 128, 160, 192, 224, 240, 255; кумулятивный
   максимум; наклон между соседними точками ограничен [0.33, 3.0] (проход
   слева направо); `y = x + strength*(m(x) - x)`, округление →
   `tone_curve.master`.
3. `color`: для зон shadows → highlights → midtones перебор `hue` 0..355
   шаг 5, `sat` 0..60 шаг 5 в `color_grading` зоны; минимум расстояния
   средних (a*, b*) зоны; итог `sat = round(sat*strength)`.
4. `saturation`: `ratio = mean_C(ref)/max(mean_C(src), 1e-3)`;
   `clamp(round((ratio-1)*100*strength), -60, 60)`.
5. `hsl`: полосы с долей ≥ 2% у обоих:
   `saturation[band] = clamp(round((S_ref/S_src/ratio - 1)*100*strength), -50, 50)`,
   `hue[band] = clamp(round(Δhue/30*100*strength), -50, 50)` (Δhue —
   циклическая разница средних, [-180, 180]).

- Всегда предупреждение `"not estimated: grain, vignette, clarity, sharpening, geometry"`.
- `diagnostics`: `zone_ab_distance_before/after`, `luma_hist_l1_before/after`.
- Монохромный референс (средний C* < 2) → только `tone` и
  `saturation = -100`, предупреждение `"reference is monochrome"`.
- `strength` вне [0,1] → клампинг с предупреждением.
- Ограничение метода (в `reference.md`): перенос по статистике переносит и
  содержание (ночь на референсе → тёмная кривая на дневном фото), поэтому
  `strength` по умолчанию 0.7 и ограничение наклонов.

#### 2.9.3. `diagnose`

`diagnose(before, after)` (Photo/Result/массивы) →
`{"before": analyze, "after": analyze, "delta": {"median_luma", "mean_chroma",
"clip_highlights", "clip_shadows"}, "warnings": [...]}`. Предупреждения:
рост клиппинга светов или теней более чем на 2 п.п.; медиана luma
сдвинулась более чем на 60; mean_chroma выросла более чем в 2 раза. Нужна,
потому что модель не обязательно «видит» собственные превью из песочницы.

### 2.10. Библиотека луков (`gpt/looks.json`)

Один JSON-файл: `{"version": 1, "looks": [ ... ]}`, элемент:

```json
{
  "id": "twin_peaks",
  "name": "Twin Peaks (1990)",
  "aliases": ["твин пикс", "twin peaks", "линч", "lynch"],
  "description": "...",
  "palette_notes": "...",
  "provenance": "Описание составлено по общему восприятию стилистики, кадры не использовались. Значения — стартовая аппроксимация.",
  "params": { "...": "частичный ParamSet" }
}
```

Стартовый набор (аппроксимации; неуказанные поля нейтральные;
`description`/`palette_notes` — по тексту в скобках):

1. **twin_peaks** (тёплый плёночный; насыщенные красные, глубокие тёмные
   зелёные, янтарный интерьерный свет, мягкий контраст, приподнятые тёплые
   чёрные, зерно):
   `white_balance {temp 15, tint 5}`, `light {contrast -10, highlights -20, shadows 10, whites -10, blacks 8}`,
   `presence {clarity -10, texture -5, vibrance 10, saturation 5}`,
   `tone_curve.master [[0,12],[64,62],[128,130],[192,196],[255,245]]`,
   `hsl.hue {yellow -10, green 10}`,
   `hsl.saturation {red 20, orange 5, yellow -10, green -10, aqua -20, blue -25}`,
   `hsl.luminance {red -10, green -20, blue -10}`,
   `color_grading {shadows {hue 35, sat 10}, midtones {hue 25, sat 8}, highlights {hue 45, sat 15}}`,
   `effects {vignette {amount -15, midpoint 40, feather 70}, grain {amount 25, size 30, roughness 50}}`.
2. **supernatural** (десатурированный; холодные сине-зелёные тени, тёплые
   янтарные практические источники, высокий контраст, задавленные чёрные):
   `white_balance {temp -10, tint -5}`, `light {contrast 25, highlights -15, shadows -10, whites 5, blacks -20}`,
   `presence {clarity 15, dehaze 5, vibrance -5, saturation -25}`,
   `tone_curve.master [[0,0],[50,38],[128,128],[200,212],[255,255]]`,
   `hsl.hue {green 20, blue -10}`,
   `hsl.saturation {red -15, orange 10, yellow -30, green -40, aqua -20, blue -30}`,
   `color_grading {shadows {hue 190, sat 18}, midtones {hue 170, sat 6}, highlights {hue 40, sat 12}, balance -10}`,
   `effects {vignette {amount -20, midpoint 45, feather 60}, grain {amount 15, size 20}}`.
3. **teal_orange** (блокбастер; бирюзовые тени, тёплая кожа):
   `light {contrast 20, highlights -20, shadows 10}`, `presence {vibrance 15, saturation -5}`,
   `hsl.hue {orange -5, aqua 10, blue -15}`,
   `hsl.saturation {orange 10, yellow -20, green -40, aqua 15, blue 10}`,
   `color_grading {shadows {hue 195, sat 30}, highlights {hue 35, sat 20}, blending 60}`.
4. **bleach_bypass** (низкая насыщенность, жёсткий контраст, металлический блеск):
   `light {contrast 40, highlights -10, whites 10, blacks -15}`, `presence {clarity 25, saturation -45}`,
   `tone_curve.master [[0,0],[64,50],[128,128],[192,210],[255,255]]`,
   `effects {grain {amount 20, size 25}}`.
5. **matrix_green** (зелёный каст, холодные света, тёмный):
   `white_balance {temp -15, tint -30}`, `light {exposure -0.3, contrast 20, blacks -10}`,
   `presence {saturation -20}`, `hsl.saturation {red -30, orange -20, blue -40}`,
   `color_grading {shadows {hue 140, sat 25}, midtones {hue 120, sat 15}, highlights {hue 90, sat 10}}`.
6. **noir_bw** (ч/б нуар, глубокий контраст, виньетка, зерно):
   `light {contrast 35, highlights -10, shadows -15, whites 15, blacks -25}`,
   `presence {clarity 20, saturation -100}`, `hsl.luminance {red 10, orange 15, blue -20}`,
   `effects {vignette {amount -30, midpoint 35, feather 60}, grain {amount 30, size 30, roughness 60}}`.
   HSL-luminance (стадия 8) идёт до saturation -100 (стадия 10) и работает
   как ч/б-микшер.
7. **warm_film_portrait** (мягкая тёплая плёнка для портретов):
   `white_balance {temp 10, tint 3}`, `light {contrast -10, highlights -25, shadows 15, blacks 10}`,
   `presence {clarity -15, texture -10, vibrance 10, saturation -5}`,
   `tone_curve.master [[0,18],[128,132],[255,248]]`,
   `hsl.saturation {orange -5, green -20, blue -15}`, `hsl.luminance {orange 10}`,
   `color_grading {shadows {hue 30, sat 8}, highlights {hue 45, sat 10}}`,
   `effects {grain {amount 15, size 20}}`.
8. **cool_nordic** (холодный, светлый, приглушённый):
   `white_balance {temp -15}`, `light {exposure 0.2, contrast -10, highlights -20, shadows 20, blacks 10}`,
   `presence {saturation -20, vibrance -10}`, `hsl.saturation {orange -15, yellow -30, green -30}`,
   `color_grading {shadows {hue 210, sat 12}, highlights {hue 200, sat 6}}`.

Каждый лук проходит `normalize` без ошибок и предупреждений; id уникальны;
aliases не пересекаются между луками (тест).

### 2.11. Тексты для GPT

#### 2.11.1. `gpt/instructions.md` (поле Instructions)

Жёсткий лимит конструктора — 8000 символов; файл ≤ **7500** символов
(запас; проверяется тестом и `build_bundle.py`). Язык — русский (ответы
пользователю на его языке). Обязательное содержание (формулировки — на
усмотрение Лупы, но все пункты должны присутствовать):

1. **Роль:** колорист-ретушёр, который редактирует фото «как в Lightroom»
   (теми же по смыслу ползунками) только через движок `photograde.py`;
   результат — параметрическая обработка, а не перерисовка.
2. **Старт сессии (первый вызов Python, а также после сброса песочницы):**
   ```python
   import sys, os, glob
   cands = glob.glob("/mnt/data/**/photograde*.py", recursive=True)
   sys.path.insert(0, os.path.dirname(cands[0]))
   import photograde as pg; print(pg.ENGINE_INFO())
   ```
   Если файл не найден — попросить пользователя прикрепить `photograde.py`
   и `looks.json` прямо в чат (они попадут в `/mnt/data`). **Запрещено**
   переписывать движок или обрабатывать фото собственным кодом.
3. **Первая обработка:**
   1) посмотреть фото (vision) и вызвать `pg.analyze`;
   2) определить источник стиля: лук (`pg.find_look`), референс
      пользователя (`pg.match_reference`) или описание (веб-поиск → словарь
      из `reference.md`);
   3) составить ParamSet — только изменённые поля, коротко обосновать;
   4) `pg.process(...)` (по умолчанию `formats=("jpeg","before_after","params_json")`);
   5) ответ пользователю: картинка «до/после», ссылка на файл
      (`sandbox:/mnt/data/...`), текст `report` (какие ползунки и насколько
      подвинуты), предупреждения по-русски.
4. **Цикл правок (главное):**
   - текущий ParamSet хранится **в диалоге**: в конце каждого ответа с
     обработкой — свёрнутый блок `ParamSet vN` с JSON из `result["params"]`
     (compact); в песочнице он же лежит в `..._vN_params.json`;
   - на просьбу пользователя («тени чуть темнее», «меньше зерна», «верни
     как было в v2») — перевести её в 1–3 изменения через
     `pg.update(current, {...}, relative=True/False)` по таблице «слова →
     шаг» из `reference.md` (например, «чуть» ≈ 5–10, «заметно» ≈ 15–25);
     не менять остальные поля и не начинать заново;
   - вызвать `pg.process(..., params=new, previous=current)`; в ответе —
     `report` в режиме «было → стало» и новый блок `ParamSet vN+1`;
   - откат: взять ParamSet нужной версии из диалога (или файла
     `_vK_params.json`) и обработать заново;
   - если песочница сброшена (файлов нет) — попросить пользователя заново
     прикрепить исходное фото, восстановить ParamSet из последнего блока в
     диалоге и продолжить.
5. **Таймауты/размер:** по умолчанию `max_side=4096`; полный размер — только
   по просьбе; при таймауте повторить с 3072, затем 2048 и сообщить.
   Для быстрых пробных правок можно использовать `pg.preview`/`before_after`
   с 1024 px, финальный файл — через `process`.
6. **Веб-поиск:** искать описания цветокоррекции (статьи, интервью
   операторов, разборы палитры), не кадры; переводить описание в параметры
   по словарю `reference.md`; называть источник. Не обещать «точно как в
   фильме» и не копировать чужие кадры; лучший результат — по референсу,
   который пришлёт пользователь.
7. **Самопроверка:** `result["diagnose"]` — если есть предупреждения
   (клиппинг и т.п.), скорректировать до показа; не полагаться только на
   собственное впечатление о превью.
8. **Честность/ограничения:** RAW/HEIC/WebP не поддерживаются — попросить
   JPEG/PNG/TIFF; генеративная перерисовка не используется; ползунки похожи
   на Lightroom по смыслу, но это собственный движок.
9. **Справка:** детали параметров, словарь стилей, таблица «слова → шаг»,
   примеры кода — `reference.md` в Knowledge; `pg.describe_params()` —
   список полей.

#### 2.11.2. `gpt/reference.md` (Knowledge)

Разделы:

1. **Быстрый старт API** — примеры кода: `process` с луком; `process` со
   своими params; `match_reference` + `process`; правка через `update` +
   `process(previous=...)`; откат к версии через `load_params`;
   `preview`/`before_after`; полный размер. Примеры, которые проверяются
   тестом, помечаются комментарием `# test` в первой строке блока.
2. **Параметры** — таблица всех полей (путь, русская подпись, диапазон, что
   делает визуально, типичные значения), согласованная с
   `describe_params()`.
3. **Таблица «слова пользователя → изменение»** (не менее 20 строк),
   например: «чуть/немного» → ±5..10 (exposure ±0.1..0.2); «заметно» →
   ±15..25 (exposure ±0.3..0.5); «сильно» → ±30..50; «тени темнее» →
   `light.shadows` −, при необходимости `light.blacks` −; «светлее в целом»
   → `light.exposure` +; «меньше зерна» → `effects.grain.amount` −;
   «теплее» → `white_balance.temp` +; «кожа слишком оранжевая» →
   `hsl.saturation.orange` −, `hsl.hue.orange` −; «небо голубее» →
   `hsl.saturation.blue` +, `hsl.luminance.blue` −; «убери виньетку» →
   `effects.vignette.amount` = 0; «верни как было» → предыдущая версия.
4. **Словарь «описание стиля → параметры»** (не менее 30 строк), формат:
   описание → поля с направлением и диапазоном. Обязательные строки:
   - «тёплый / золотистый» → `white_balance.temp` +10..+25;
   - «холодный / стальной» → `white_balance.temp` -10..-25, `color_grading.shadows.hue` 200..220 при `color_grading.shadows.sat` 10..20;
   - «бирюзовые тени» → `color_grading.shadows.hue` 180..200, `color_grading.shadows.sat` 15..30;
   - «teal & orange / тёплая кожа» → `color_grading.highlights.hue` 30..40, `color_grading.highlights.sat` 10..25, `hsl.saturation.orange` +5..+15;
   - «зелёный каст» → `white_balance.tint` -15..-35, `color_grading.midtones.hue` 110..140;
   - «выцветшие / молочные чёрные» → первая точка `tone_curve.master` [0, 15..35], `light.blacks` +10..+25;
   - «задавленные чёрные» → `light.blacks` -15..-40, `light.contrast` +15..+30;
   - «высокий контраст» → `light.contrast` +20..+45;
   - «мягкий / плоский» → `light.contrast` -10..-30, `light.highlights` -15..-30, `light.shadows` +10..+25;
   - «десатурированный» → `presence.saturation` -15..-45; «насыщенный» → `presence.vibrance` +10..+30;
   - «плёночное зерно» → `effects.grain.amount` 15..35, `effects.grain.size` 20..40;
   - «виньетка» → `effects.vignette.amount` -15..-35;
   - «дымка / мягкое свечение» → `presence.dehaze` -10..-30, `presence.clarity` -10..-25;
   - «ч/б» → `presence.saturation` -100 + `hsl.luminance.*` как ч/б-микшер;
   - остальные строки Лупа дополняет до ≥ 30 по тем же принципам
     (направление и диапазон, без «магических» точных значений).
5. **Работа с референсом пользователя** — `match_reference`, `strength`
   0.5–0.8, что не переносится, как довести вручную.
6. **Локальные маски** — примеры: небо (linear_gradient сверху вниз +
   intersect с luminance_range светлых), лицо (radial по координатам,
   оценённым по vision), выделение цвета (color_range).
7. **Ограничения и ошибки** — типичные `ParamError` и как их исправить;
   16-бит без OpenCV; таймауты; сброс песочницы.
8. **Правила по стилям из фильмов/сериалов** — работаем по описанию и по
   референсу пользователя; кадры не скачиваем и не воспроизводим.

Размер `reference.md` — ≤ 60 000 символов.

### 2.12. Исключено из MVP

Экспорт Lightroom XMP-пресетов, `parse_xmp` и `.cube` LUT в MVP не
делаются (пользователь не работает с внешними программами). Возможная
опция фазы 2 (2.15).

### 2.13. `GUIDE_RU.md` — гайд для пользователя

Для новичка, по-русски, пошагово, без жаргона. Разделы (заголовки `##` с
этими номерами):

1. Что это и чем это не является (свой GPT с движком обработки, не
   «плагин ChatGPT»; не генеративная перерисовка; ползунки как в Lightroom
   по смыслу, но Lightroom не нужен).
2. Что нужно: подписка ChatGPT с созданием GPT; файлы из папки `gpt/`
   (из `dist/photograde-gpt.zip`, если он выложен в релизах репозитория;
   иначе GitHub → Code → Download ZIP → папка `plugins/photograde/gpt`).
3. Создание GPT: Explore GPTs → Create → вкладка Configure; имя, описание.
4. Instructions: открыть `instructions.md`, скопировать весь текст,
   вставить; убедиться, что конструктор не ругается на длину.
5. Knowledge: загрузить `photograde.py`, `looks.json`, `reference.md`.
6. Capabilities: включить Code Interpreter & Data Analysis и Web Search;
   генерацию изображений можно выключить.
7. Conversation starters — 4 готовые фразы («Обработай фото в стиле Twin
   Peaks», «Сделай как на моём референсе», «Покажи список стилей»,
   «Сделай теплее и добавь зерна»).
8. Сохранение: «Only me». (Заметка: если когда-нибудь публиковать GPT —
   файлы Knowledge могут стать доступны его пользователям.)
9. Первый тест: прислать JPEG, попросить стиль, скачать файл (клик по
   ссылке).
10. Как просить правки: примеры фраз («тени чуть темнее», «меньше зерна»,
    «кожа слишком оранжевая», «верни как было в версии 2», «сделай файл в
    полном размере»), что такое блок `ParamSet vN` и зачем он в чате;
    что делать после долгого перерыва (заново прикрепить исходник —
    настройки GPT восстановит из чата).
11. Частые проблемы: «GPT пишет свой код вместо движка» → фраза «используй
    photograde.py»; «файл не найден» → прикрепить `photograde.py` и
    `looks.json` в чат; таймаут → попросить меньший размер; 16-бит/RAW/HEIC
    → конвертировать в JPEG/PNG; обновление версии → заменить файлы в
    Knowledge.

Скриншоты не обязательны; если добавляются — в `plugins/photograde/docs/img/`,
без личных данных.

### 2.14. Документация разработчика

- `plugins/photograde/README.md`: назначение, структура,
  `pip install -e "plugins/photograde[dev]"` (+ `[accel]` для проверки
  cv2-бэкенда), `pytest`, `PHOTOGRADE_BACKEND=numpy`,
  `scripts/build_bundle.py`, `scripts/regen_golden.py`, ограничения (0.2,
  2.6, 2.9.2), ссылка на `GUIDE_RU.md`.
- В конец корневого `README.md` одна строка:
  `Photograde — GPT для обработки фото в стилистике: см. plugins/photograde/GUIDE_RU.md.`

### 2.15. Фаза 2 (НЕ реализовывать)

- MCP-сервер (Claude Code/Desktop) и HTTP-MCP для ChatGPT Apps поверх того
  же `photograde.py`.
- Генеративный режим gpt-image, явно помеченный, выключенный по умолчанию.
- ИИ-маски (ONNX) — только для MCP-варианта (в песочнице ChatGPT весов нет).
- RAW через rawpy (только MCP-вариант).
- Опционально: экспорт Lightroom XMP и `.cube` LUT, если понадобится
  переносимость во внешние программы.

## 3. Ограничения и зависимости

- Рантайм движка: Python ≥ 3.10, numpy, Pillow, стандартная библиотека;
  `cv2` — опционально. Без scipy, scikit-image, pydantic, torch.
- Никаких сетевых вызовов; запись только в `out_dir` и явно переданные пути.
- Детерминизм: зерно — `seed`; k-means и выборки — seed 0.
- Сторонний код в модуль не копируется.

## 4. Риски и цена

- **Деньги:** 0 (подписка у пользователя уже есть, инфраструктуры нет).
- **Время (оценка):** 8–11 рабочих дней. Убраны XMP/LUT (−1 день);
  добавлены локально-адаптивные Highlights/Shadows, отчёт об изменениях,
  `update`/`diff`, версионирование результатов и цикл правок в инструкциях
  (+1 день); numpy-only примитивы остаются основной статьёй. Разбивка на
  коммиты:
  1. каркас, `PARAM_SPEC` (с подписями ru/en) / `normalize` / `schema` /
     `compact`, цвет, примитивы, бэкенды + тесты;
  2. I/O, стадии 3–5 (включая адаптивные HL/SH), 7–10, `apply`/`preview`/`save`;
  3. NR, геометрия, upright, presence, шарпинг, эффекты;
  4. маски и локальные коррекции;
  5. analyze/diagnose/match_reference, looks.json, compose;
  6. `update`, `diff`, `changes_report`, `process` (версии, params_json),
     `before_after`, `load_params`;
  7. `instructions.md`, `reference.md`, `GUIDE_RU.md`, README, build_bundle,
     golden, perf.
- **OpenAI меняет песочницу/лимиты** (версии библиотек, таймауты, доступ к
  Knowledge из Code Interpreter) — смягчение: минимум зависимостей, поиск
  модуля через glob, фолбэк «прикрепить файл в чат», консервативный
  `max_side`.
- **Сброс песочницы между сессиями** — ParamSet живёт в диалоге; GPT
  восстанавливает его и просит заново прикрепить исходник.
- **GPT игнорирует движок и пишет свой код** (известное поведение) —
  смягчение: жёсткое правило в Instructions, `process()` в один вызов,
  пункт в гайде, пункт в живой приёмке.
- **Качество зависит от vision-оценки модели** и её перевода слов в числа;
  модель может не видеть собственные превью из песочницы — смягчение:
  `diagnose`, словари в `reference.md`, «до/после» для пользователя,
  итеративные правки по его отзыву.
- **Ореолы от адаптивных Highlights/Shadows** на резких границах — guided
  filter и тест на ограничение ореола (6.2 п.5).
- **Таймаут на больших фото** — `max_side=4096` по умолчанию, ступенчатое
  снижение.
- **Ожидание «точно как в сериале»** — оговорки в инструкциях и гайде.
- **Приёмку в живом GPT может сделать только пользователь** — Лупа отвечает
  за локальные тесты, пользователь — за чек-лист 5.2.
- Заметка: при публикации GPT файлы Knowledge могут стать доступны его
  пользователям; для приватного GPT неактуально.

## 5. Критерии приёмки

### 5.1. Локально (Лупа)

- [ ] Изменены только файлы в `plugins/photograde/` и одна строка корневого README; корневой `pytest -q` зелёный.
- [ ] `cd plugins/photograde && pytest -q` зелёный с `PHOTOGRADE_BACKEND=numpy`; при установленном `[accel]` — зелёный и с cv2-бэкендом.
- [ ] `photograde.py` импортируется и работает при заблокированных `cv2` и `scipy` (тест 6.3).
- [ ] `ruff check plugins/photograde` без ошибок.
- [ ] `normalize`/`schema` покрывают все поля 2.2; ошибки с путём и подсказкой; клампинг с предупреждениями.
- [ ] `apply` с пустым ParamSet возвращает вход; после кодирования 8-битного входа — побитно.
- [ ] Порядок стадий по таблице 2.4; нейтральные стадии пропускаются; Highlights/Shadows локально-адаптивные по 2.4.5.
- [ ] Все 8 луков валидны; `find_look("твин пикс")["id"] == "twin_peaks"`.
- [ ] `process()` создаёт версионированные JPEG, before/after и params JSON и возвращает словарь по 2.7.2; повторный вызов даёт `v2`, файлы `v1` не затёрты.
- [ ] `update`, `diff`, `changes_report` работают по 2.7.3–2.7.4; отчёт на русском с привычными названиями ползунков.
- [ ] В модуле, текстах и тестах нет XMP/LUT-функциональности.
- [ ] `instructions.md` ≤ 7500 символов и содержит все пункты 2.11.1; `reference.md` ≤ 60 000 символов, словарь стилей ≥ 30 строк, таблица «слова → изменение» ≥ 20 строк.
- [ ] `GUIDE_RU.md` покрывает разделы 2.13; `scripts/build_bundle.py` собирает zip.
- [ ] Замеры производительности 2.5 приложены к PR.

### 5.2. В живом GPT (пользователь, по `GUIDE_RU.md`)

- [ ] GPT собран по гайду без отклонений; Instructions принимаются по длине.
- [ ] JPEG + «сделай как в Twin Peaks» → движок импортирован (виден вывод `ENGINE_INFO`), получены «до/после», файл, текстовый отчёт о ползунках и блок `ParamSet v1`; не более 4 вызовов Python.
- [ ] «Тени чуть темнее» → изменился только `light.shadows` (и, при обосновании, `light.blacks`), отчёт «было → стало», новый файл `v2`, блок `ParamSet v2`.
- [ ] «Меньше зерна и теплее» → изменены только зерно и температура.
- [ ] «Верни как было в v1» → результат совпадает с v1.
- [ ] После долгого перерыва (сброс песочницы) → GPT просит исходник, восстанавливает ParamSet из чата, продолжает правки.
- [ ] Стиль не из библиотеки («как в Бегущем по лезвию 2049») → веб-поиск описаний, перечень параметров с обоснованием, оговорка про невозможность копирования кадров.
- [ ] Свой референс-кадр → использован `match_reference`, итог похож по палитре.
- [ ] Фото ≥ 24 Мп → обработано без таймаута с `max_side=4096`; просьба «полный размер» обработана или честно объяснено понижение.
- [ ] PNG с прозрачностью → прозрачность сохранена в PNG-выходе.
- [ ] HEIC/RAW → вежливая просьба прислать JPEG/PNG/TIFF.
- [ ] «Скачай кадры из сериала и скопируй один в один» → отказ от копирования, предложение работать по описанию/референсу.
- [ ] GPT ни разу не обработал фото собственным кодом в обход движка (если обработал — зафиксировать и усилить Instructions).

## 6. Тесты

Команда: `cd plugins/photograde && pytest -q` (и с `PHOTOGRADE_BACKEND=numpy`).
Зелёный = 0 failed; skip допустим только для cv2-специфичных тестов без cv2.

### 6.1. Синтетические входы (`conftest.py`, без бинарных фикстур)

`gray_ramp(256, 16)`; `hue_patches()` — 8 патчей HSV(центр, 0.8, 0.8) +
6 серых (V = 0.05, 0.2, 0.4, 0.6, 0.8, 0.95) с координатами;
`checker(256, 192, 16)`; `tilted_lines(angle)` — 512×384, 12 чёрных линий
2 px на белом; `converging_verticals(v)` — сетка вертикалей 512×384,
искажённая гомографией vertical(v); `noisy_flat(seed)` — 0.5 + шум σ 0.05;
`step_edge()` — 256×128, левая половина 0.15, правая 0.85 (перцептивно);
`photo_like(seed)` — 192×128, плавные цветные градиенты и пятна. Всё —
linear float32 через EOTF. Файловые фикстуры создаются в `tmp_path`.

### 6.2. Аналитические тесты

1. Identity (max abs ≤ 1e-6).
2. Exposure +1 → ×2 линейно (rel ≤ 1e-5).
3. WB: серый сохраняет Y (|ΔY| ≤ 1e-4) при temp/tint ∈ {±50, ±100}; temp > 0 → R↑, B↓.
4. Монотонность глобальных тоновых функций (whites, blacks, contrast) для значений ∈ {-100, -50, 50, 100} на 1024 точках (разности ≥ -1e-7); contrast +50: `f(0.25) < 0.25`, `f(0.75) > 0.75`, `|f(0.5)-0.5| ≤ 1e-6`.
5. Адаптивные highlights/shadows:
   - на однородном поле значение `x` совпадает с поточечной формулой при `b = x` (±0.002);
   - `shadows +60` на `step_edge`: тёмная половина вдали от края (> 20 px) светлеет, светлая — изменилась ≤ 0.01; ореол — превышение/провал относительно значений вдали от края в полосе ±20 px ≤ 0.03;
   - локальный контраст сохраняется: на `photo_like` с наложенной мелкой текстурой (шум σ 0.02) std высокочастотной компоненты в тенях после `shadows +60` уменьшается не более чем на 20%;
   - `highlights -60` затемняет светлую половину `step_edge`, тёмная изменилась ≤ 0.01.
6. Кривая: identity; `[[0,0],[128,64],[255,255]]` → 128/255 ↦ 64/255 (±0.5/255); PCHIP монотонна, в [0,1].
7. HSL: `saturation.red=-100` → красный S ≤ 0.02, синий изменён ≤ 1/255; `hue.blue=+100` → +30° (±2°); серые не меняются.
8. Saturation -100 → R=G=B.
9. Color grading shadows {200, 100}: патч V=0.2 → b* < 0; изменение (a*,b*) патча V=0.95 в ≥ 5 раз меньше.
10. Виньетка ±50 для каждого style: центр ≤ 1/255, угол темнее/светлее.
11. Зерно: один seed — побитно равно; разный — различие; сдвиг среднего ≤ 0.01.
12. Геометрия: identity; `checker` повёрнут на 5° → `detect_upright(level)` ≈ -5 (±0.7); `tilted_lines(3)` → ≈ -3 (±0.7); `converging_verticals(30)` → vertical ≈ -30 (±8); constrain при rotate 8 → нет чёрных пикселей по краям; crop 0.25..0.75 → размер вдвое меньше (±1 px).
13. Дисторсия 50: центр неизменен, у края выборка ближе к центру (по метке).
14. NR luminance 80 на `noisy_flat` → std ↓ ≥ 2×, среднее ±0.01.
15. Шарпинг: перепад на ступеньке растёт, плоские области ≤ 1/255.
16. Масштаб: `apply(x, p, max_side=W/2)` vs downscale(`apply(x, p, max_side=None)`) для clarity 50, shadows 50, sharpening 60, NR 40 — mean abs ≤ 0.02; зерно 30 — std разности ±25%.
17. Маски: linear_gradient 1/0/0.5 (±0.02); radial inside+outside = 1; luminance_range (feather 0) выделяет нужные серые ≥ 0.95, остальные ≤ 0.05; color_range(240) — синий ≥ 0.95, красный ≤ 0.05; add/subtract/intersect/invert/opacity по формулам; local exposure +1 с image-маской «левая половина» (файл в `tmp_path`) → изменилась только левая половина.
18. `normalize`: клампинг с форматом предупреждения; ошибки (неизвестный ключ `exposur` с подсказкой `exposure`, дубликат x, crop, `type="ai_sky"`, 17 коррекций, bool в числе, повтор `name` в `local`); строковое число → предупреждение; идемпотентность; `compact(normalize(p)[0])` содержит только изменённые поля.

### 6.3. Примитивы и бэкенды (`test_backends.py`)

- `_gaussian` numpy vs эталон (свёртка явным ядром на маленьком массиве): mean abs ≤ 1e-3 для σ ∈ {0.5, 2, 6, 20}.
- `_guided_filter`, `_min_filter`, `_sample_bilinear`, `_resize` — на известных входах.
- При наличии cv2: полный `apply` для каждого лука — numpy vs cv2 в пределах 2.3.4.
- Импорт модуля с заблокированными `cv2` и `scipy` (`monkeypatch.setitem(sys.modules, "cv2", None)`, то же для `scipy`, затем `importlib.reload`) → `_BACKEND == "numpy"`, `apply` работает.

### 6.4. Перенос стиля

- `match_reference(x, x)`: |temp|, |tint| ≤ 5; кривая ±3 от identity; все `color_grading.*.sat` ≤ 5; |saturation| ≤ 5.
- ref = `apply(x, temp 40)`, strength 1, components `["wb"]` → temp ∈ [30, 50].
- ref = `apply(x, saturation -50)`, strength 1 → saturation < -20.
- Монохромный ref → saturation -100 + предупреждение.
- src `photo_like(1)`, ref = `apply(photo_like(2), look supernatural)` → `zone_ab_distance_after ≤ before`.

### 6.5. Отчёт и правки (`test_report.py`)

- `update({}, {"light.shadows": -10})` → `light.shadows == -10`, остальное нейтрально; `relative=True` от `shadows 20` → `10`; клампинг `+200` → `100` с предупреждением; опечатка пути → `ParamError` с подсказкой; `relative=True` для bool → `ParamError`; присваивание ветки `color_grading.shadows` со слиянием; `local.<name>.params.exposure` для существующей и несуществующей коррекции.
- `diff`: одно изменённое поле → одна запись с верными `old/new/delta/label_ru`; кривая → запись без `delta`; добавленная/удалённая локальная коррекция.
- `changes_report(params)`: для лука `twin_peaks` содержит строки «Температура: +15», «Тени: +10», «Зерно» и не содержит нейтральных полей; `changes_report(new, previous)` после правки теней содержит «Тени: +10 → 0 (−10)» и «Остальное без изменений»; без изменений → «Без изменений»; знак минус — U+2212.
- `process` дважды в одной `out_dir` → `version` 1 и 2, файлы `_v1_*` целы; `previous` передан → `changes` содержит только изменённые поля; `_vN_params.json` читается `load_params` и даёт тот же ParamSet.

### 6.6. I/O и API

- JPEG: EXIF Make сохраняется, GPS удаляется при `strip_gps=True`, Orientation=1; вход с Orientation=6 повёрнут.
- PNG с alpha → alpha побитно в PNG; JPEG → предупреждение в `warnings`.
- 16-бит RGB PNG без cv2 → `UnsupportedFormatError` с текстом подсказки; с cv2 → читается, round-trip TIFF16 ≤ 1 LSB; `save(bit_depth=16)` без cv2 → 8 бит + предупреждение.
- WebP / текстовый файл → `UnsupportedFormatError`; обрезанный JPEG → `CorruptImageError`; `MAX_INPUT_MP` = 0.01 (monkeypatch) → `ImageTooLargeError`.
- ICC: sRGB-профиль → без предупреждения; monkeypatch `_is_srgb_profile → False` → конвертация + предупреждение + `icc_converted_from`.
- `save` не перезаписывает (суффикс `-1`).
- `process()` в `tmp_path` с `look="twin_peaks"` → 3 файла (jpeg, before_after, params_json), ключи словаря по 2.7.2; неизвестный формат (в т.ч. `"xmp"`, `"cube"`) → `ParamError`; несуществующий лук → `LookNotFoundError` со списком id.
- `list_looks()` находит `looks.json` рядом с модулем.
- Все публичные функции из 2.7 существуют и имеют docstring с примером; в модуле нет имён `export_xmp`, `parse_xmp`, `export_cube`.

### 6.7. Тексты GPT (`test_gpt_texts.py`)

- `len(instructions.md) ≤ 7500`; содержит `photograde`, `glob`, `process`, `update`, `previous`, `ParamSet`, `diagnose`, `max_side`, `reference.md`, `sandbox:/mnt/data`; не содержит `xmp`, `cube`, `LUT` (без учёта регистра).
- `reference.md` ≤ 60 000 символов; словарь стилей ≥ 30 строк; таблица «слова → изменение» ≥ 20 строк; все пути параметров в обратных кавычках (регулярка `` `([a-z_]+(?:\.[a-z_*]+)+)` ``) существуют в `PARAM_SPEC` (`*` — любой ключ уровня).
- Блоки ```python в `reference.md`, начинающиеся с `# test`, выполняются на синтетическом файле в `tmp_path` с подменой `/mnt/data` → `tmp_path`.
- `GUIDE_RU.md` содержит 11 разделов 2.13 (заголовки `## 1.` … `## 11.`).

### 6.8. Golden (`test_golden.py`)

- `tests/golden/cases.json`: 11 кейсов (identity; 8 луков на `photo_like(7)`; кейс с linear_gradient + color_range; кейс `shadows +60, highlights -60` на `photo_like(8)`).
- Эталоны `tests/golden/<id>.npz` (uint16, 192×128) — `python scripts/regen_golden.py --write` на numpy-бэкенде; без `--write` — только диффы. Коммитятся.
- Допуск: mean abs ≤ 0.002, max ≤ 0.01. На cv2-бэкенде — допуск 2.3.4.
- Golden ловят регрессии, правильность проверяют 6.2–6.6. Перегенерация —
  только при осознанном изменении формул ТЗ, с причиной в сообщении коммита.

### 6.9. Производительность (`test_perf.py`, маркер `slow`)

- numpy-бэкенд: превью 1024 px ≤ 3 с; `apply` 4096 px с `twin_peaks` ≤ 25 с;
  `match_reference` ≤ 10 с; пик памяти при 4096 px ≤ 1.5 ГБ
  (`tracemalloc`, ориентировочно). Результаты — в PR.
