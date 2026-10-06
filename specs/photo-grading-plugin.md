# ТЗ: Photograde — плагин параметрической обработки фото «в стилистике X» для LLM-агента

Статус: **рабочий вариант с допущениями.** Открытые вопросы к пользователю
перечислены в разделе 0.4; до ответа на них реализация идёт по допущениям
A1–A7. Если ответ пользователя противоречит допущению — правится этот файл,
а не код «по месту».

## 0. Контекст

### 0.1. Что хочет пользователь

Пользователь присылает фото и просит обработать его «в стилистике»
(например, цветокоррекция как в сериале Twin Peaks или Supernatural). Агент
подбирает стиль (по встроенной библиотеке «луков» или по референс-кадру) и
выполняет цветокоррекцию и прочую обработку в терминах параметров
Lightroom: свет, баланс белого, кривые, HSL, детализация, оптика/геометрия,
эффекты, локальные маски. Результат — обработанный файл плюс
переиспользуемый пресет (Lightroom XMP и `.cube` LUT).

### 0.2. Ключевые архитектурные решения (обязательны к прочтению)

1. **Модель-генератор изображений не может «подтягивать плагин».**
   gpt-image-2 / gpt-image-2.5 (OpenAI выпустила Images 2.5 08.09.2026,
   в API — `gpt-image-2.5-flare` и `gpt-image-2.5-sunburst`) — это модели,
   которые получают промпт/картинку и возвращают картинку. Инструменты
   (tools) вызывает агентский рантайм: LLM-ассистент в Claude Code / Claude
   Desktop (MCP), ChatGPT (Apps SDK поверх MCP или Custom GPT Actions),
   OpenAI Responses/Agents API (function tools / remote MCP). Поэтому
   плагин — это **MCP-сервер с инструментами**, которые вызывает LLM-агент
   с vision; генератор изображений в основном контуре не участвует.
2. **Обработка — детерминированная и параметрическая, а не генеративная.**
   Генеративное редактирование (images/edits) перерисовывает кадр:
   дрейф лиц и мелких деталей, галлюцинации, ограничение разрешения
   (порядка 2K), потеря EXIF и исходного качества. Это не цветокоррекция.
   Схема плагина:
   `LLM-агент (vision) → ParamSet (JSON) → движок на numpy/OpenCV → файл + XMP + LUT`.
   Агент только выбирает параметры и смотрит превью; пиксели меняет код.
3. **Референсы.** Плагин не скачивает кадры из сериалов. Источники стиля:
   (а) встроенная библиотека описаний луков (`looks/*.json` — параметры и
   описание палитры, никаких кадров); (б) референс-кадр, который приложил
   пользователь → алгоритмический подбор параметров (`match_reference`);
   (в) веб-поиск — вне плагина: если у агента-хоста есть свой веб-поиск,
   он может использовать его для текстового описания стиля и затем
   настроить параметры; плагин URL не принимает (см. раздел 3).
4. **Численное совпадение с рендером Lightroom — не цель.** Параметры
   повторяют семантику и диапазоны Lightroom, но алгоритмы свои. XMP-пресет,
   открытый в Lightroom, даст похожий, но не идентичный результат. Это
   документируется в README плагина и в отчёте `export`.

### 0.3. Допущения (до ответа пользователя)

- **A1. Рантайм:** локальный MCP-сервер (stdio) на Python для Claude Code /
  Claude Desktop + CLI. Ядро не зависит от MCP, чтобы позже обернуть его в
  HTTP-MCP для ChatGPT Apps или в function tools OpenAI API.
- **A2. Форматы:** JPEG, PNG, TIFF (8/16 бит), WebP — в ядре. HEIC —
  опционально через extra `heic`. RAW — опционально через extra `raw`
  (rawpy/LibRaw). Тесты RAW пропускаются, если rawpy не установлен.
- **A3. Выход:** обработанный файл (JPEG/TIFF16/PNG) + Lightroom XMP-пресет
  + `.cube` LUT. Все три входят в MVP.
- **A4. Автопоиск референсов в интернете:** не реализуется в плагине.
- **A5. Генеративный режим (gpt-image):** не входит в MVP, описан в 2.13
  как фаза 2.
- **A6. ИИ-маски (небо, человек, объект):** не входят в MVP, фаза 2
  (2.8.3). В MVP — геометрические маски и маски по диапазонам.
- **A7. Размещение в репозитории:** отдельный пакет `plugins/photograde/`
  со своим `pyproject.toml`. Пакет `reviewer` не затрагивается.

### 0.4. Открытые вопросы к пользователю

1. Где должен жить плагин: Claude Code / Claude Desktop (MCP), ChatGPT
   (Custom GPT / Apps — нужен публичный HTTPS-сервер), OpenAI API-агент,
   или всё сразу?
2. Нужна ли поддержка RAW и с каких камер (CR3, NEF, ARW, RAF, DNG)?
3. Какой результат нужен: только картинка / + XMP / + LUT?
4. Насколько обязателен автопоиск референсов в интернете, или достаточно
   библиотеки луков + референса от пользователя?
5. Нужны ли ИИ-маски (небо/человек/кожа) в первой версии?
6. Нужен ли вообще генеративный режим gpt-image, и есть ли бюджет на
   платный API?

## 1. Что уже работает (не ломать)

- Репозиторий содержит сервис `reviewer` (Triple-Pass Text Reviewer):
  `src/reviewer/**`, `app.py`, `tests/*.py`, корневой `pyproject.toml`
  (пакет `reviewer`, `testpaths = ["tests"]`), `requirements.txt`,
  `Dockerfile`, `scripts/deploy_hf.py`, `landing/`.
- **Запрещено** менять файлы вне `plugins/photograde/`, кроме одной строки
  в корневом `README.md` (2.14). В частности, не трогать корневой
  `pyproject.toml`, `requirements.txt`, `Dockerfile` — зависимости плагина
  (numpy, opencv) не должны попасть в сборку `reviewer` и в деплой на HF
  (`scripts/deploy_hf.py` заливает только `app.py`, `requirements.txt`,
  `README.md`, `src/` — `plugins/` туда не попадает, так и должно остаться).
- Корневой прогон `pytest -q` (тесты `reviewer`) должен оставаться зелёным
  и не должен собирать тесты плагина.

## 2. Задача

### 2.1. Структура пакета

Создать:

```
plugins/photograde/
  pyproject.toml
  README.md                 # установка, подключение к Claude Code, ограничения
  AGENT_GUIDE.md            # инструкция агенту (отдаётся как MCP prompt)
  scripts/regen_golden.py   # перегенерация golden-эталонов
  src/photograde/
    __init__.py             # __version__ = "0.1.0"
    errors.py               # PhotogradeError и наследники (см. ниже)
    schema.py               # ParamSet (pydantic v2), диапазоны, normalize_params, JSON Schema
    color.py                # sRGB OETF/EOTF, luma, RGB<->HSV, linear sRGB<->Lab (D65)
    io.py                   # загрузка/сохранение, ICC, EXIF, ориентация, RAW, alpha
    pipeline.py             # render(img, params, scale) — порядок стадий 2.4
    stages/
      __init__.py
      noise.py  geometry.py  wb.py  tone.py  presence.py
      curve.py  hsl.py  grading.py  saturation.py  local.py
      sharpen.py  effects.py
    masks.py                # построение масок (2.8)
    geometry_detect.py      # авто-горизонт/вертикали (2.4.3)
    analyze.py              # статистика изображения (2.9.1)
    match.py                # подбор ParamSet по референсу (2.9.2)
    looks.py                # загрузка библиотеки луков, compose
    looks/*.json            # 8 луков (2.10)
    export_xmp.py           # Lightroom XMP (2.11)
    export_cube.py          # .cube LUT (2.12)
    session.py              # хранилище загруженных фото
    mcp_server.py           # MCP-инструменты (2.7)
    cli.py                  # typer CLI (2.7.3)
  tests/
    conftest.py             # синтетические изображения (6.1)
    golden/cases.json
    golden/*.npz
    test_schema.py test_color.py test_io.py test_stages_*.py test_pipeline.py
    test_masks.py test_geometry_detect.py test_match.py test_looks.py
    test_export_xmp.py test_export_cube.py test_mcp_tools.py test_cli.py test_golden.py
```

`errors.py`: `PhotogradeError(Exception)`; наследники
`UnsupportedFormatError`, `CorruptImageError`, `ImageTooLargeError`,
`GeometryError`, `UnknownPhotoError`, `LookNotFoundError`.

`pyproject.toml` плагина:

- `name = "photograde"`, `version = "0.1.0"`, `requires-python = ">=3.11"`,
  layout `src/`, build-backend setuptools (как в корне).
- `dependencies`: `numpy>=1.26`, `opencv-python-headless>=4.9`,
  `Pillow>=10.3`, `pydantic>=2.6`, `typer>=0.12`, `mcp>=1.2`.
- `optional-dependencies`: `raw = ["rawpy>=0.19"]`,
  `heic = ["pillow-heif>=0.16"]`, `dev = ["pytest>=8.0", "ruff>=0.6"]`.
  Extras `ai` и `generative` в MVP не создавать.
- `project.scripts`: `photograde = "photograde.cli:app"`,
  `photograde-mcp = "photograde.mcp_server:main"`.
- `package-data`: `photograde/looks/*.json`.
- `[tool.pytest.ini_options] testpaths = ["tests"]`, маркер `slow`
  зарегистрирован, по умолчанию `addopts = "-m 'not slow'"`.
- `[tool.ruff] line-length = 100`, `select = ["E", "F", "I"]`.

### 2.2. Схема параметров (`schema.py`)

Pydantic v2-модели, у всех `model_config = ConfigDict(extra="forbid")`
(опечатка LLM в имени ключа = ошибка валидации с именем поля). Все поля
имеют дефолт = «нейтрально», поэтому допускается частичный ParamSet.
Диапазоны повторяют Lightroom.

Нотация: `int[-100..100]=0` — целое, диапазон, дефолт. `float` — шаг 0.01,
если не указано иное.

```
ParamSet
  version: Literal[1] = 1
  white_balance:
    temp:  int[-100..100]=0      # относительный сдвиг (как у LR для JPEG)
    tint:  int[-100..100]=0      # + = маджента, - = зелёный
  light:
    exposure:   float[-5.0..5.0]=0.0   # EV
    contrast:   int[-100..100]=0
    highlights: int[-100..100]=0
    shadows:    int[-100..100]=0
    whites:     int[-100..100]=0
    blacks:     int[-100..100]=0
  presence:
    texture:    int[-100..100]=0
    clarity:    int[-100..100]=0
    dehaze:     int[-100..100]=0
    vibrance:   int[-100..100]=0
    saturation: int[-100..100]=0
  tone_curve:                     # точки [x, y], x,y int 0..255
    master: list[[int,int]] = [[0,0],[255,255]]
    red:    list[[int,int]] = [[0,0],[255,255]]
    green:  list[[int,int]] = [[0,0],[255,255]]
    blue:   list[[int,int]] = [[0,0],[255,255]]
  hsl:                            # Color: red, orange, yellow, green, aqua, blue, purple, magenta
    hue:        dict[Color, int[-100..100]]  (отсутствующий ключ = 0)
    saturation: dict[Color, int[-100..100]]
    luminance:  dict[Color, int[-100..100]]
  color_grading:
    shadows:    {hue: int[0..359]=0, sat: int[0..100]=0, lum: int[-100..100]=0}
    midtones:   {hue, sat, lum}
    highlights: {hue, sat, lum}
    global_:    {hue, sat, lum}     # в JSON — ключ "global" (alias)
    blending:   int[0..100]=50
    balance:    int[-100..100]=0
  detail:
    sharpening:
      amount:  int[0..150]=0
      radius:  float[0.5..3.0]=1.0  # пиксели полного разрешения, шаг 0.1
      detail:  int[0..100]=25
      masking: int[0..100]=0
    noise_reduction:
      luminance:          int[0..100]=0
      luminance_detail:   int[0..100]=50
      luminance_contrast: int[0..100]=0
      color:              int[0..100]=0
      color_detail:       int[0..100]=50
      color_smoothness:   int[0..100]=50
  lens:
    distortion:          int[-100..100]=0   # + исправляет бочку
    vignetting:          int[-100..100]=0   # + осветляет углы (коррекция объектива)
    vignetting_midpoint: int[0..100]=50
    chromatic_aberration:
      remove:      bool=False             # авто-коррекция латеральной ХА
      red_cyan:    int[-100..100]=0       # ручная
      blue_yellow: int[-100..100]=0       # ручная
  transform:
    upright:    Literal["off","level","vertical"]="off"   # авто, см. 2.4.3
    vertical:   int[-100..100]=0
    horizontal: int[-100..100]=0
    rotate:     float[-10.0..10.0]=0.0    # градусы, шаг 0.1
    aspect:     int[-100..100]=0
    scale:      int[50..150]=100
    offset_x:   float[-100..100]=0.0
    offset_y:   float[-100..100]=0.0
    constrain:  bool=True                 # авто-масштаб без пустых краёв
  crop: null | {left, top, right, bottom: float[0..1], angle: float[-45..45]=0}
                                          # доли кадра; left<right, top<bottom
  effects:
    vignette:
      amount:     int[-100..100]=0
      midpoint:   int[0..100]=50
      roundness:  int[-100..100]=0
      feather:    int[0..100]=50
      highlights: int[0..100]=0
      style: Literal["highlight_priority","color_priority","paint_overlay"]="highlight_priority"
    grain:
      amount:    int[0..100]=0
      size:      int[0..100]=25
      roughness: int[0..100]=50
      seed:      int>=0 = 0
  local: list[LocalAdjustment] = []   # максимум 16 элементов
```

`LocalAdjustment` — раздел 2.8.

**Нормализация.** `normalize_params(raw: dict) -> tuple[ParamSet, list[str]]`:

- Неизвестные ключи и неверные типы → `pydantic.ValidationError`
  (пробрасывается наружу; MCP-инструмент возвращает текст ошибки).
- Числа вне диапазона **клампятся** к границе; для каждого клампа в список
  предупреждений добавляется строка вида
  `"light.exposure: 7.0 -> 5.0 (clamped)"`. Дробное число в int-поле
  округляется (без предупреждения).
- Кривые: точки сортируются по x; дубликаты x → ошибка; меньше 2 или
  больше 16 точек → ошибка; координаты вне 0..255 клампятся с
  предупреждением.
- `crop`: `left >= right` или `top >= bottom` → ошибка.
- `hsl`: неизвестный цвет → ошибка.
- `local`: больше 16 элементов → ошибка.

`param_json_schema() -> dict` — `ParamSet.model_json_schema(by_alias=True)`,
отдаётся инструментом `get_param_schema`.

### 2.3. Цветовая модель (`color.py`)

- Рабочее пространство движка: **линейный RGB с праймериз sRGB/Rec.709,
  float32, значения ≥ 0, без верхнего клампа** (превышение 1.0 = пересвет,
  клампится только при кодировании результата).
- Перцептивное представление = sRGB OETF (кусочная формула
  IEC 61966-2-1) от линейных значений; для значений > 1 — продолжение
  степенной ветки. EOTF — обратная функция.
- Luma: `0.2126 R + 0.7152 G + 0.0722 B`. «Линейная luma» `Y` — на линейных
  значениях, «перцептивная luma» `l` — та же формула на перцептивных.
- RGB↔HSV — векторизованно на numpy, hue в градусах [0, 360).
- linear sRGB ↔ CIE Lab (D65, стандартная матрица sRGB→XYZ).
- Функции принимают `np.ndarray` формы (H, W, 3) float32 и возвращают ту же
  форму.

### 2.4. Пайплайн (`pipeline.py`)

`render(img_linear: np.ndarray, params: ParamSet, *, scale: float = 1.0,
original_long_edge: int | None = None) -> RenderResult`, где
`RenderResult(image: np.ndarray, warnings: list[str], applied_upright: dict | None)`.

`scale` = (длинная сторона обрабатываемого изображения) / (длинная сторона
оригинала); `original_long_edge` по умолчанию = длинная сторона входа.
Все радиусы в пикселях (NR, шарпинг, clarity, зерно, кисти) умножаются на
`scale`, чтобы превью и полноразмерный экспорт выглядели одинаково.
Пиксельные константы ниже заданы для **оригинала**.

Порядок стадий (фиксированный; стадия с нейтральными параметрами
пропускается без вычислений):

| # | Стадия | Модуль | Пространство |
|---|--------|--------|--------------|
| 1 | Шумоподавление | `stages/noise.py` | перцептивное |
| 2 | Геометрия: дисторсия + ХА + transform + crop (один remap); коррекция виньетирования объектива | `stages/geometry.py` | линейное |
| 3 | Баланс белого | `stages/wb.py` | линейное |
| 4 | Экспозиция | `stages/tone.py` | линейное |
| 5 | Whites/Blacks → Highlights/Shadows → Contrast | `stages/tone.py` | перцептивная luma |
| 6 | Dehaze → Clarity → Texture | `stages/presence.py` | перцептивное |
| 7 | Tone Curve: master, затем R/G/B | `stages/curve.py` | перцептивное |
| 8 | HSL / Color Mixer | `stages/hsl.py` | перцептивное (HSV) |
| 9 | Color Grading | `stages/grading.py` | перцептивное |
| 10 | Vibrance, Saturation | `stages/saturation.py` | перцептивное |
| 11 | Локальные коррекции | `stages/local.py` | по параметру |
| 12 | Шарпинг | `stages/sharpen.py` | перцептивная luma |
| 13 | Виньетка (post-crop) | `stages/effects.py` | см. 2.4.13 |
| 14 | Зерно | `stages/effects.py` | перцептивное |

**Почему порядок отличается от «WB → тон → кривая → HSL → детали → оптика
→ эффекты → маски»:** шумоподавление идёт до тональных операций (иначе
поднятые тени усиливают шум; в LR NR тоже привязано к ранней стадии);
геометрия — до всего остального, чтобы виньетка и зерно ложились на
финальный кадр, а маски задавались в координатах финального кадра;
локальные коррекции — до шарпинга и эффектов (в LR зерно и виньетка
накладываются поверх локальных правок).

Каждая стадия — функция `apply(img, params_group, ctx) -> img`, где
`ctx: StageContext(scale, original_long_edge, warnings)`. Контракт: между
стадиями изображение передаётся в линейном пространстве; стадия сама
переводит его в нужное пространство и обратно. Оптимизация «конвертировать
только на границах групп стадий» допустима, если golden-тесты не меняются.

Обозначения ниже: `x` — перцептивное значение 0..1, `s(t) = sin(πt)²`,
`smoothstep(a,b,x)` — стандартный (с клампингом), `clamp01`,
`gaussian(img, sigma)` — `cv2.GaussianBlur` с `ksize=(0,0)`.

#### 2.4.1. Шумоподавление (`noise.py`)

- Luminance (`luminance > 0`), `L = luminance/100`: перевести перцептивный
  RGB в YCrCb (`cv2.cvtColor`, float32). К Y:
  `Y_den = cv2.bilateralFilter(Y, d=0, sigmaColor=0.02 + 0.10*L, sigmaSpace=(1 + 4*L)*scale)`;
  `Y' = lerp(Y_den, Y, 0.5*luminance_detail/100)`;
  `Y' += (luminance_contrast/100) * 0.25 * (Y - gaussian(Y, 2*scale))`.
- Color (`color > 0`), `sigma = (color/100)*8*scale`: для каналов Cr, Cb
  `blur = gaussian(c, sigma)`; при `color_smoothness > 0` —
  `blur = lerp(blur, gaussian(c, 2*sigma), color_smoothness/100*0.5)`;
  `c' = lerp(blur, c, 0.5*color_detail/100)`.
- sigma < 0.3 → соответствующий шаг пропускается.

#### 2.4.2. Геометрия (`geometry.py`)

Один вызов `cv2.remap` на канал (каналы отдельно ради ХА), интерполяция
`INTER_CUBIC` при `scale == 1`, иначе `INTER_LINEAR`;
`borderMode=BORDER_CONSTANT`, значение 0. Результат клампится снизу к 0
(cubic даёт отрицательные выбросы).

Обратное отображение для каждого пикселя выхода `p_out`:

1. Нормированные координаты: центр кадра = (0,0), половина диагонали = 1.
2. Crop: `p_out` переводится в координаты некадрированного кадра
   (масштаб/смещение по прямоугольнику crop, поворот на `crop.angle` вокруг
   центра прямоугольника). Размер выхода = размер прямоугольника crop в
   пикселях.
3. Transform: `p = H⁻¹ · p`, где `H` — композиция (в порядке применения к
   изображению): vertical, horizontal, rotate, aspect, scale, offset.
   - vertical `v`: гомография по 4 углам (`cv2.getPerspectiveTransform`):
     верхняя кромка растягивается по ширине относительно центра с
     множителем `k = 1 + 0.4*v/100`, нижняя без изменений.
   - horizontal `h`: аналогично, правая кромка по высоте, `k = 1 + 0.4*h/100`.
   - rotate: поворот на `rotate` градусов против часовой стрелки вокруг центра.
   - aspect `a`: `sx = 1 + a/200`, `sy = 1 - a/200`.
   - scale: `sx *= scale/100`, `sy *= scale/100`.
   - offset: сдвиг на `offset_x/100 * W/2`, `offset_y/100 * H/2`.
   - `constrain=True`: бинарным поиском (20 итераций, множитель 1.0..3.0)
     подобрать дополнительный масштаб, при котором 4 угла и 4 середины
     кромок выхода после обратного отображения (включая дисторсию)
     попадают внутрь источника. Если ×3.0 не хватает →
     `GeometryError("transform too strong")`.
4. Дисторсия: `r_s = r * (1 + k1 * r²)`, `k1 = -0.25 * distortion/100`.
5. ХА (только R и B): радиус дополнительно умножается на
   `mR = 1 + 0.02 * red_cyan/100` и `mB = 1 + 0.02 * blue_yellow/100`
   (до ±2% на краю). При `remove=True` `mR`, `mB` подбираются автоматически
   (ручные значения игнорируются): для каждого канала перебор множителя
   в [0.995, 1.005] шагом 0.0005; критерий — максимум корреляции модуля
   градиента канала с модулем градиента G по кольцу r ∈ [0.6, 1.0] на копии
   с длинной стороной 1024.
6. Перевод в пиксельные координаты источника.

Коррекция виньетирования объектива (после remap, линейное пространство):
`gain = 1 + (vignetting/100) * smoothstep(m, 1.0, r)`,
`m = 0.8 * vignetting_midpoint/100`, `r` — нормированный радиус выхода;
`img *= gain`.

#### 2.4.3. Авто-горизонт и вертикали (`geometry_detect.py`)

`detect_upright(img_linear, mode: Literal["level","vertical"]) -> dict`
с ключами `rotate: float, vertical: int, confidence: float, lines_used: int`.

- Копия с длинной стороной 1024 px, перцептивная luma, Гаусс sigma=1,
  `cv2.Canny` (пороги 50/150 на uint8), `cv2.HoughLinesP`
  (`rho=1, theta=π/360, threshold=80, minLineLength=0.05*diag, maxLineGap=0.01*diag`).
- `level`: линии с |α| < 20° к горизонтали; `rotate = -weighted_median(α)`,
  вес = длина линии. Если таких линий < 3 — линии с |α−90°| < 20°, угол
  отклонения от вертикали. Клампинг ±10°.
  `confidence = min(1, суммарная длина использованных линий / (2*diag))`.
- `vertical`: сначала `level`; затем перебор `v ∈ [-100..100]` шагом 2:
  применить гомографию vertical (2.4.2) к концам почти-вертикальных линий
  (|α−90°| < 25°), минимизировать дисперсию их углов.
- Если `lines_used < 3` → `confidence = 0`, `rotate = 0`, `vertical = 0`,
  предупреждение `"upright: not enough lines"`.
- В пайплайне при `transform.upright != "off"` `detect_upright` вызывается
  на входном изображении **до** геометрии; найденные значения
  **прибавляются** к ручным `rotate`/`vertical` (с клампингом) и
  возвращаются в `RenderResult.applied_upright`.

#### 2.4.4. Баланс белого (`wb.py`)

Линейное пространство, поканальные множители:
`gR = 2^(0.35*temp/100)`, `gB = 2^(-0.35*temp/100)`, `gG = 2^(-0.35*tint/100)`;
затем `g /= (0.2126*gR + 0.7152*gG + 0.0722*gB)` (серый сохраняет яркость).
Для RAW as-shot WB камеры применяется при декодировании (2.6), затем —
этот относительный сдвиг.

#### 2.4.5. Экспозиция и тон (`tone.py`)

- Exposure: `img *= 2^exposure` (линейно).
- На перцептивной luma `x = OETF(Y)` последовательно:
  - whites `w = whites/100`: `x += 0.2 * w * min(x,1)^4`
  - blacks `b = blacks/100`: `x += 0.2 * b * (1 - min(x,1))^4`
  - highlights `h = highlights/100`: `t = clamp01((x-0.5)/0.5)`, `x += 0.12 * h * s(t)`
  - shadows `sh = shadows/100`: `t = clamp01(x/0.5)`, `x += 0.12 * sh * s(t)`
  - contrast `a = 0.5*contrast/100`: для x ∈ [0,1] `x = x - a * sin(2πx)/(2π)`;
    x > 1 не меняется.
  - итог: `x' = max(x, 0)`.
- Все функции монотонны на [0,1] во всём диапазоне параметров (тест).
- Применение с сохранением оттенка: `Y' = EOTF(x')`,
  `rgb *= Y' / max(Y, 1e-6)`.
- Highlights/Shadows — **глобальные поточечные** операции, в отличие от
  локально-адаптивных в LR. Осознанное упрощение: стадия полностью
  представима в LUT. Фиксируется в README.

#### 2.4.6. Presence: Dehaze, Clarity, Texture (`presence.py`)

Пространственные операции (в LUT не переносятся), перцептивное пространство.

- Dehaze `d = dehaze/100`:
  - `d > 0`: dark channel = min по каналам → `cv2.erode` квадратным ядром
    `max(3, round(15*scale))`; атмосферный свет `A` (RGB) = среднее по
    пикселям из верхних 0.1% dark channel; `t = 1 - 0.95 * dark / max(A)`,
    сгладить `cv2.blur` ядром `max(3, round(40*scale))`, `t = max(t, 0.1)`;
    `J = (I - A)/t + A`; результат `max(lerp(I, J, d), 0)`.
  - `d < 0`: `k = 0.4*|d|`, `a` = средняя перцептивная luma верхних 1%
    пикселей; `I' = I*(1-k) + a*k`.
- Clarity `c = clarity/100`, перцептивная luma `l`:
  `detail = l - gaussian(l, 0.008*original_long_edge*scale)`;
  `Δ = 0.8 * c * detail * 4*l*(1-l)`; `rgb += Δ` (на каждый канал).
- Texture `tx = texture/100`: `detail` с `sigma = 0.002*original_long_edge*scale`,
  `Δ = 0.6 * tx * detail`, без весовой функции по тону.

#### 2.4.7. Tone Curve (`curve.py`)

- Интерполяция точек — монотонная кубическая Fritsch–Carlson (PCHIP), без
  выбросов за 0..255. Реализовать самостоятельно (без scipy).
- Кривая табулируется в 4096 значений на [0,1]; применение — `np.interp`
  к каждому каналу перцептивного RGB, предварительно клампированному к [0,1].
- master применяется к R, G, B; затем `red` к R, `green` к G, `blue` к B.
- Тождественная кривая → шаг пропускается.

#### 2.4.8. HSL (`hsl.py`)

- Перцептивный RGB (клампированный к [0,1]) → HSV.
- Центры полос (HSV hue): red 0, orange 30, yellow 60, green 120, aqua 180,
  blue 240, purple 270, magenta 300. Вес пикселя по полосам — кусочно-
  линейная интерполяция между двумя соседними центрами по кругу (сумма = 1).
- Hue: `H' = (H + Σ w_i * hue_i/100 * 30) mod 360`.
- Saturation: `S' = clamp01(S * (1 + Σ w_i * sat_i/100))`.
- Luminance: `V' = clamp01(V * (1 + Σ w_i * lum_i/100 * 0.5 * S))`
  (вес S — нейтральные пиксели не меняются).
- HSV → RGB.

#### 2.4.9. Color Grading (`grading.py`)

- `l` — перцептивная luma; положительный `balance` смещает границу в
  сторону светов: `l_b = clamp01(l + balance/200)`.
- `p = 3 - 2*blending/100` (blending 0 → узкие зоны, 100 → широкие).
- Веса: `w_s = (1 - l_b)^p`, `w_h = l_b^p`, `w_m = max(0, 1 - w_s - w_h)`;
  для global `w = 1`.
- Для каждой зоны: `c = hsv2rgb(hue, 1, 1)`, `tint = c - luma(c)`;
  `rgb += w * (sat/100 * 0.15 * tint + lum/100 * 0.15)`.
- Результат клампится снизу к 0.

#### 2.4.10. Vibrance и Saturation (`saturation.py`)

- `l` — перцептивная luma, `S` — HSV-насыщенность.
- Vibrance `v = vibrance/100`: `k = 1 + v * (1 - S) * skin`, `skin = 0.5`,
  если HSV hue ∈ [10°, 50°], иначе 1; `rgb = l + (rgb - l) * k`.
- Saturation: `rgb = l + (rgb - l) * (1 + saturation/100)`; при -100 —
  R=G=B=l.
- Результат клампится снизу к 0.

#### 2.4.11. Локальные коррекции — раздел 2.8.

#### 2.4.12. Шарпинг (`sharpen.py`)

- Перцептивная luma `l`; `hp = l - gaussian(l, radius*scale)`.
- Ограничение ореолов: `hp = clamp(hp, -lim, lim)`, `lim = 0.05 + 0.25*detail/100`.
- Маска краёв: `e` — модуль Собеля от `gaussian(l, 1*scale)`, делённый на
  его 99-й перцентиль (если перцентиль 0 → `e = 0`);
  `m = smoothstep(t0, t0 + 0.1, e)`, `t0 = 0.3*masking/100`; при
  `masking = 0` → `m = 1`.
- `rgb += (amount/150) * 1.5 * hp * m` (на каждый канал).

#### 2.4.13. Виньетка post-crop и зерно (`effects.py`)

- Виньетка. Координаты нормируются так, что эллипс по пропорциям кадра
  проходит через углы при `r = 1`. `roundness`: 0 — эллипс по пропорциям
  кадра; +100 — круг, проходящий через углы; -100 — супер-эллипс с
  показателем 4 по пропорциям кадра; промежуточные значения — линейная
  интерполяция расстояний. Маска
  `m = smoothstep(m0, m0 + (1 - m0) * (0.05 + 0.95*feather/100), r)`,
  `m0 = 0.9*midpoint/100`.
  - `highlight_priority` (линейное пространство): `f = 2^(1.5 * amount/100 * m)`;
    при amount < 0: `f = lerp(f, 1, smoothstep(0.7, 1.0, Y) * highlights/100)`;
    `rgb *= f`.
  - `color_priority` (перцептивное, сохраняет оттенок):
    `l' = l + 0.6 * amount/100 * m * (l if amount < 0 else 1 - l)`,
    `rgb *= l' / max(l, 1e-6)`.
  - `paint_overlay` (перцептивное):
    `rgb = lerp(rgb, 0 if amount < 0 else 1, 0.8 * |amount|/100 * m)`.
- Зерно (перцептивное): `rng = np.random.default_rng(seed)`; монохромный
  шум `N(0,1)` на сетке `(ceil(H/k), ceil(W/k))`,
  `k = max(1, (1 + 3*size/100) * scale)`, апсемпл до (H, W) `INTER_CUBIC`
  → `n1`; второй октав с `max(1, k/2)` → `n2`; `r = roughness/100`,
  `n = (1-r)*n1 + r*n2`, нормировать на std = 1;
  `rgb += n * 0.08 * amount/100 * (0.5 + 2*l*(1-l))`.
  Одинаковые `seed`, параметры и размер → побитно одинаковый результат.

#### 2.4.14. Кодирование результата

Клампинг [0,1], OETF, квантование `np.rint` в uint8 (JPEG/PNG/WebP) или
uint16 (TIFF16/PNG16).

### 2.5. Производительность и память

- Превью: длинная сторона `PHOTOGRADE_PREVIEW_PX` (по умолчанию 1600),
  ресайз `cv2.INTER_AREA` в линейном пространстве.
- Цели: превью 1600 px со всеми глобальными стадиями ≤ 1.5 с на 4-ядерном
  CPU; полный рендер 24 Мп ≤ 20 с, пиковая память ≤ 3 ГБ (float32 RGB
  24 Мп ≈ 290 МБ на буфер; промежуточные буферы освобождать).
- Лимит входа `PHOTOGRADE_MAX_MP` (по умолчанию 60 Мп), больше →
  `ImageTooLargeError`.
- Проверки производительности — тесты с маркером `slow`, в обязательный
  прогон не входят.

### 2.6. Ввод/вывод (`io.py`)

`load_image(path) -> LoadedImage` (dataclass):
`linear: np.ndarray (H,W,3) float32`, `alpha: np.ndarray | None` (float32 0..1),
`source_format: str`, `bit_depth: int`, `is_raw: bool`, `exif: bytes | None`,
`icc_converted_from: str | None`, `warnings: list[str]`, `path: Path`.

- Ориентация EXIF применяется при загрузке (`ImageOps.exif_transpose`);
  при сохранении тег Orientation = 1.
- ICC: функция `_is_srgb_profile(icc_bytes: bytes) -> bool` — описание
  профиля (`ImageCms.getProfileDescription`) содержит `"sRGB"`
  (регистронезависимо). 8-битное изображение со встроенным профилем, для
  которого она возвращает False (Display P3, Adobe RGB) → конвертация в
  sRGB через `ImageCms.profileToProfile` (intent perceptual),
  предупреждение `"converted from <описание> to sRGB"`. 16 бит с не-sRGB
  профилем — профиль игнорируется, предупреждение
  `"16-bit ICC profile ignored, treated as sRGB"`. Нет профиля — sRGB без
  предупреждения.
- 16-битные TIFF/PNG читаются `cv2.imread(..., IMREAD_UNCHANGED)`
  (BGR(A) → RGB(A)), 8-битные — Pillow.
- Grayscale → RGB. CMYK → RGB (Pillow `convert`) с предупреждением.
  Многокадровые файлы → первый кадр + предупреждение.
- Alpha хранится отдельно и прикрепляется при сохранении в PNG/TIFF; при
  сохранении в JPEG — отбрасывается с предупреждением. Геометрия (2.4.2)
  применяется и к alpha тем же remap (без ХА).
- RAW (расширения `.cr2 .cr3 .nef .arw .raf .dng .orf .rw2 .pef .srw`,
  регистронезависимо): без `rawpy` →
  `UnsupportedFormatError("RAW support requires: pip install photograde[raw]")`.
  Иначе `rawpy.imread(path).postprocess(use_camera_wb=True, no_auto_bright=True,
  output_bps=16, gamma=(1, 1), output_color=rawpy.ColorSpace.sRGB)` → /65535
  → linear. EXIF для RAW не переносится (предупреждение). Поддержка
  конкретных моделей (в т.ч. CR3) зависит от версии LibRaw в колесе
  rawpy — фиксируется в README.
- HEIC/HEIF: при установленном `pillow-heif` регистрируется opener; иначе
  `UnsupportedFormatError` с подсказкой `photograde[heic]`.
- Прочие неподдерживаемые расширения → `UnsupportedFormatError`.
- Повреждённый файл → `CorruptImageError` с исходным сообщением.
- Пикселей больше лимита → `ImageTooLargeError` (проверка по размеру из
  заголовка до декодирования, где формат это позволяет).

`save_image(img_linear, alpha, path, fmt, quality=95, exif=None) -> Path`:
форматы `jpeg` (8 бит, встроенный sRGB ICC, EXIF сохраняется), `png`
(8 бит), `png16`, `tiff16` (через `cv2.imwrite`), `webp`. Существующий
файл не перезаписывается — к имени добавляется `-1`, `-2`, …

### 2.7. Инструменты агента

#### 2.7.1. Сессия (`session.py`)

- `Session` хранит загруженные фото: `photo_id` = первые 12 hex-символов
  sha256 содержимого файла. Хранит `LoadedImage`, превью (linear, длинная
  сторона `PREVIEW_PX`, если оригинал больше) и его `scale`.
- Рабочая папка `PHOTOGRADE_WORKDIR` (по умолчанию `~/.cache/photograde`),
  подпапки `previews/`, `exports/`; создаются при старте.
- LRU на 8 фото; при вытеснении массивы освобождаются.
- Неизвестный `photo_id` → `UnknownPhotoError("unknown photo_id, call load_photo first")`.

#### 2.7.2. MCP-сервер (`mcp_server.py`)

Официальный Python SDK `mcp`, `FastMCP("photograde")`, транспорт stdio,
`main()` запускает сервер. Каждый инструмент — тонкая обёртка над функцией
ядра; функции-обработчики устроены так, чтобы их можно было вызвать в
тестах без запуска процесса. `PhotogradeError` и `ValidationError`
возвращаются как ошибка инструмента с человекочитаемым текстом, без
трейсбека.

Превью отдаются как MCP `ImageContent` (JPEG, качество 85), чтобы агент
видел результат.

| Инструмент | Вход | Выход |
|---|---|---|
| `load_photo` | `path: str` | `{photo_id, width, height, format, bit_depth, is_raw, has_alpha, warnings}` + превью |
| `get_param_schema` | — | JSON Schema ParamSet |
| `list_looks` | — | `[{id, name, aliases, description}]` |
| `get_look` | `look_id: str` | `{id, name, description, palette_notes, provenance, params}` |
| `analyze_image` | `photo_id: str \| None`, `path: str \| None` (ровно одно) | статистика (2.9.1) |
| `detect_upright` | `photo_id`, `mode: "level" \| "vertical"` | `{rotate, vertical, confidence, lines_used}` |
| `match_reference` | `photo_id`, `reference_path`, `strength: float = 0.7`, `components: list[str] = ["wb","tone","color","saturation","hsl"]` | `{params, diagnostics, warnings}` |
| `apply_params` | `photo_id`, `params: dict = {}`, `look_id: str \| None`, `look_amount: float = 1.0` | `{preview_path, params_effective, warnings, applied_upright}` + превью |
| `compare` | `photo_id`, `params: dict = {}`, `look_id: str \| None`, `look_amount: float = 1.0` | изображение «до \| после» (каждая половина длинной стороной 800, разделитель 4 px белый) |
| `export` | `photo_id`, `params: dict = {}`, `look_id`, `look_amount`, `formats: list[str]` (из `jpeg`,`tiff16`,`png`,`png16`,`webp`,`xmp`,`cube`; по умолчанию `["jpeg","xmp","cube"]`), `out_dir: str \| None`, `name: str \| None`, `quality: int = 95`, `xmp_target: "rendered" \| "raw" \| None` (None → `raw`, если фото RAW, иначе `rendered`) | `{files: {fmt: path}, mapping_report: {xmp: [...], cube: [...]}, warnings}` |

Итоговый ParamSet при `look_id` + `params` (`looks.compose(look, amount, params)`):
`blend(look.params, amount)`, поверх — явные значения `params` (глубокое
слияние по ключам; явные значения побеждают; `local` — конкатенация:
сначала из лука, потом из params). `amount` вне [0, 1] — клампинг с
предупреждением. `blend`:
- числовые поля с нейтралью 0 умножаются на amount (с округлением для
  int-полей);
- не масштабируются: `color_grading.*.hue`, `color_grading.blending`,
  `grain.seed`, `grain.size`, `grain.roughness`, `vignette.midpoint`,
  `vignette.roundness`, `vignette.feather`, `vignette.highlights`,
  `vignette.style`, `sharpening.radius/detail/masking`,
  `noise_reduction.*_detail`, `noise_reduction.color_smoothness`,
  `lens.vignetting_midpoint`, булевы и строковые поля;
- `transform.scale` → `round(100 + amount*(v - 100))`;
- кривые → `y = round(x + amount*(y - x))` поточечно.
`look_id` не найден → `LookNotFoundError` со списком доступных id.

Имя выходных файлов по умолчанию: `<имя исходника>_<look_id или "graded">.<ext>`.

MCP prompt `grade_photo` отдаёт содержимое `AGENT_GUIDE.md`.

#### 2.7.3. CLI (`cli.py`, typer)

- `photograde apply IN [--params P.json] [--look ID] [--amount 1.0] [--out OUT] [--format jpeg] [--xmp] [--cube]`
- `photograde match IN REF [--strength 0.7] -o params.json`
- `photograde looks` — список луков.
- `photograde analyze IN` — JSON статистики в stdout.
- `photograde schema` — JSON Schema в stdout.

Код возврата 0 при успехе, 2 при ошибке валидации параметров, 1 при прочих
ошибках (сообщение в stderr).

#### 2.7.4. `AGENT_GUIDE.md`

Для агента (на русском, кратко):

1. Порядок: `load_photo` → источник стиля (лук из библиотеки по имени или
   алиасу; референс от пользователя → `match_reference`; иначе — подобрать
   параметры по описанию) → `apply_params` → оценить превью → поправить
   (не более 4 итераций) → `export`.
2. Не использовать генеративные модели для цветокоррекции.
3. Правила: не превышать |exposure| 1.5 без явной причины; проверять
   клиппинг через `analyze_image`; на портретах не уводить `hsl.hue.orange`
   дальше ±15.
4. Если запрошенного стиля нет в библиотеке — предложить пользователю
   приложить референс-кадр; кадры из фильмов/сериалов самостоятельно не
   скачивать.
5. В ответе пользователю: ключевые итоговые параметры, пути к файлам,
   оговорка, что XMP в Lightroom даст похожий, но не идентичный результат,
   и перечень того, что не перенеслось в XMP/LUT (из `mapping_report`).

### 2.8. Локальные коррекции (`masks.py`, `stages/local.py`)

#### 2.8.1. Модель

```
LocalAdjustment
  name: str (1..40 символов)
  mask:
    components: list[MaskComponent]   # 1..8
    invert: bool = False
    opacity: int[0..100] = 100
  params:
    exposure: float[-4..4]=0
    contrast, highlights, shadows, whites, blacks,
    temp, tint, saturation, texture, clarity, dehaze: int[-100..100]=0

MaskComponent — один из (дискриминатор "type"); у всех
  mode: Literal["add","subtract","intersect"] = "add"
  - linear_gradient: start: [x,y], end: [x,y]          # доли кадра 0..1
  - radial: center: [x,y], radius_x, radius_y: float(0..2] (доли ширины/высоты),
            angle: float[-180..180]=0, feather: int[0..100]=50, inside: bool=True
  - luminance_range: low: int[0..100], high: int[0..100] (low <= high), feather: int[0..100]=20
  - color_range: hue: int[0..359], hue_width: int[1..180]=30,
                 sat_min: int[0..100]=10, feather: int[0..100]=30
  - brush: strokes: list[{points: list[[x,y]] (1..512), size: float(0..1] (доля длинной стороны),
                           feather: int[0..100]=50, flow: int[1..100]=100, erase: bool=False}] (1..64)
  - image: path: str   # grayscale PNG/JPEG
```

#### 2.8.2. Построение масок

- Координаты — в системе **финального кадра** (после геометрии), x вправо,
  y вниз, 0..1. Маска — float32 (H, W) в [0,1].
- linear_gradient: `t` — проекция точки на вектор start→end, нормированная
  на его длину; `m = 1 - smoothstep(0, 1, t)` (1 со стороны start, 0 со
  стороны end). `start == end` → ошибка валидации.
- radial: эллиптическое расстояние `d` с учётом `angle` (1 на границе);
  `f = max(0.01, feather/100)`; `m = 1 - smoothstep(1 - f, 1, d)`;
  `inside=False` → `1 - m`.
- luminance_range: перцептивная luma ×100; трапеция: 1 на [low, high],
  линейные склоны шириной `feather` по обе стороны (feather 0 — жёсткая
  граница). Строится по изображению **на входе стадии 11**.
- color_range: HSV того же изображения; вес по hue — трапеция с плато
  ±hue_width/2 и склонами шириной `feather/100*hue_width` (по кругу);
  умножить на `smoothstep(sat_min/100, sat_min/100 + 0.1, S)`.
- brush: для каждого мазка — float-канва, полилиния толщиной
  `max(1, round(size*long_edge))` (`cv2.polylines`, для одной точки —
  `cv2.circle`), затем Гаусс `sigma = size*long_edge*feather/100*0.5`
  (если > 0.3), умножение на `flow/100`; накопление `m = max(m, stroke)`,
  для `erase` — `m = m * (1 - stroke)`.
- image: загрузка, конвертация в L, ресайз к кадру `INTER_LINEAR`, /255;
  файл не найден → `FileNotFoundError`, не читается → `CorruptImageError`;
  оба — ошибка инструмента.
- Комбинация компонентов по порядку: первый — база (его `mode`
  игнорируется); `add` → `max(m, c)`, `subtract` → `m * (1 - c)`,
  `intersect` → `m * c`. Затем `invert` (`1 - m`), затем `* opacity/100`.

#### 2.8.3. Применение (`stages/local.py`)

Для каждой коррекции по порядку: `adjusted = apply_local_ops(img, params)`
— на копии прогоняются стадии WB (temp/tint), exposure, tone
(contrast/highlights/shadows/whites/blacks), presence
(dehaze/clarity/texture), saturation — теми же функциями и формулами, что и
глобально; затем `img = lerp(img, adjusted, mask[..., None])` в линейном
пространстве. Нейтральные params → коррекция пропускается.

**Не входит в MVP (фаза 2):** компоненты `ai_subject`, `ai_sky`,
`ai_person`, `ai_background` — через интерфейс
`MaskProvider.predict(img_perceptual, kind) -> np.ndarray` и модели ONNX
(extra `ai`). В MVP такой `type` → ошибка валидации (не молчаливый пропуск).

### 2.9. Анализ и перенос стиля по референсу

#### 2.9.1. `analyze.py`

`analyze(img_linear) -> dict` на копии с длинной стороной 512:

- `luma_percentiles`: p1, p5, p25, p50, p75, p95, p99 перцептивной luma
  (шкала 0..255, округление до 0.1).
- `clipping`: `{"highlights": доля пикселей с любым каналом ≥ 254/255,
  "shadows": доля с перцептивной luma ≤ 1/255}`.
- `zones`: для `shadows` (L* < 33), `midtones`, `highlights` (L* > 66):
  `{share, L, a, b}` (средние).
- `mean_chroma`: средний C* (Lab).
- `hue_bands`: для 8 полос — `{share, mean_saturation}` по пикселям с S > 0.15
  (полоса пикселя — ближайший центр).
- `dominant_colors`: 5 цветов `cv2.kmeans` (K=5, 10 итераций,
  `cv2.setRNGSeed(0)`, `KMEANS_PP_CENTERS`) в Lab → `[{hex, share}]`,
  сортировка по share.
- `cast_estimate`: `{a, b}` — средние по пикселям с L* 25..75 и C* < 20
  (если таких < 1% — `null`).

#### 2.9.2. `match.py`

`match_reference(src_linear, ref_linear, strength=0.7, components=ALL) -> MatchResult`
(`params: ParamSet`, `diagnostics: dict`, `warnings: list[str]`).

Оба изображения уменьшаются до длинной стороны 512 (для перебора в шаге 3 —
до 128). Шаги выполняются последовательно (только перечисленные в
`components`), каждый — на источнике, к которому применены параметры
предыдущих шагов (через `render`).

1. `wb`: перебор `temp, tint` (грубо шагом 20 по [-100..100], затем ±20
   вокруг лучшего шагом 5); цель — минимум евклидова расстояния между
   средними (a*, b*) пикселей с L* 25..75 у источника и референса.
   Итог: `temp = round(found_temp * strength)`, `tint = round(found_tint * strength)`.
2. `tone`: `m(x) = CDF_ref⁻¹(CDF_src(x))` по гистограммам перцептивной luma
   (256 бинов); выборка в x = 0, 16, 32, 64, 96, 128, 160, 192, 224, 240,
   255; принудительная монотонность (кумулятивный максимум), ограничение
   наклона между соседними точками в [0.33, 3.0] (проход слева направо);
   `y = x + strength*(m(x) - x)`, округление → `tone_curve.master`.
3. `color`: для каждой зоны перебор `hue` 0..355 шагом 5 и `sat` 0..60
   шагом 5 в `color_grading` этой зоны; минимум расстояния средних (a*, b*)
   зоны до референса; порядок зон shadows → highlights → midtones; итог
   `sat = round(sat * strength)`.
4. `saturation`: `ratio = mean_C(ref) / max(mean_C(src), 1e-3)`;
   `saturation = clamp(round((ratio - 1) * 100 * strength), -60, 60)`.
5. `hsl`: для полос с долей ≥ 2% и у источника, и у референса:
   `hsl.saturation[band] = clamp(round((S_ref / S_src / ratio - 1) * 100 * strength), -50, 50)`;
   `hsl.hue[band] = clamp(round(Δhue / 30 * 100 * strength), -50, 50)`, где
   `Δhue` — циклическая разница средних hue (градусы, в [-180, 180]).
   Остальные полосы — 0.

- Всегда в `warnings`: `"not estimated: grain, vignette, clarity, sharpening, geometry"`.
- `diagnostics`: `zone_ab_distance_before`, `zone_ab_distance_after`
  (среднее по 3 зонам расстояние средних (a*, b*) до референса),
  `luma_hist_l1_before`, `luma_hist_l1_after` (L1 между нормированными
  гистограммами luma).
- Монохромный референс (средний C* < 2) → выполняются только `tone` и
  `saturation = -100`, предупреждение `"reference is monochrome"`.
- `strength` вне [0,1] → клампинг с предупреждением.
- Ограничение метода (в README): перенос по статистике переносит и
  содержание (ночь на референсе → тёмная кривая на дневном фото), поэтому
  `strength` по умолчанию 0.7 и ограничение наклонов.

### 2.10. Библиотека луков (`looks.py`, `looks/*.json`)

Формат `looks/<id>.json`:

```json
{
  "id": "twin_peaks",
  "name": "Twin Peaks (1990)",
  "aliases": ["твин пикс", "twin peaks", "линч", "lynch"],
  "description": "Тёплый плёночный лук ...",
  "palette_notes": "Насыщенные красные, глубокие хвойные зелёные, янтарный свет ...",
  "provenance": "Описание составлено по общему восприятию стилистики, кадры не использовались. Значения — стартовая аппроксимация.",
  "params": { "...": "частичный ParamSet" }
}
```

`list_looks()`, `get_look(id)`, `find_look(query) -> Look | None`: точное
совпадение id, затем регистронезависимое совпадение с name/aliases, затем
вхождение подстроки запроса в name/aliases. `compose(look, amount, params)` —
2.7.2.

Стартовый набор (значения — аппроксимации, правятся по итогам визуальной
проверки пользователем; неуказанные поля — нейтральные). `description` и
`palette_notes` — по тексту в скобках:

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
   HSL-luminance (стадия 8) выполняется до saturation -100 (стадия 10),
   поэтому работает как ч/б-микшер.
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

Каждый файл обязан проходить `normalize_params` без ошибок и без
предупреждений (тест). Невалидный файл лука при загрузке библиотеки →
исключение (не пропуск).

### 2.11. Экспорт Lightroom XMP (`export_xmp.py`)

`export_xmp(params, name, *, target: Literal["rendered","raw"] = "rendered",
include_geometry: bool = False) -> tuple[str, list[str]]` — текст XMP и
`mapping_report` (строки о том, что не перенесено).
`parse_xmp(text) -> ParamSet` — обратное преобразование для полей таблицы
(для round-trip-теста и импорта пресетов).

Формат — пресет Lightroom Classic / Camera Raw:

```xml
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Photograde 0.1.0">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
    crs:PresetType="Normal" crs:UUID="<uuid4 hex без дефисов, верхний регистр>"
    crs:SupportsAmount="False" crs:SupportsColor="True" crs:SupportsMonochrome="True"
    crs:SupportsHighDynamicRange="True" crs:SupportsNormalDynamicRange="True"
    crs:SupportsSceneReferred="True" crs:SupportsOutputReferred="True"
    crs:Version="15.0" crs:ProcessVersion="11.0" crs:HasSettings="True"
    crs:Exposure2012="+0.50" ... >
   <crs:Name><rdf:Alt><rdf:li xml:lang="x-default">NAME</rdf:li></rdf:Alt></crs:Name>
   <crs:Group><rdf:Alt><rdf:li xml:lang="x-default">Photograde</rdf:li></rdf:Alt></crs:Group>
   <crs:ToneCurvePV2012><rdf:Seq><rdf:li>0, 0</rdf:li><rdf:li>255, 255</rdf:li></rdf:Seq></crs:ToneCurvePV2012>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
```

Генерация через `xml.etree.ElementTree` с регистрацией префиксов `x`,
`rdf`, `crs`. Числа со знаком форматируются как `+N` / `-N` / `0`;
exposure — 2 знака после точки (`+0.50`); `SharpenRadius` — 1 знак.
Пишутся служебные атрибуты и только поля, отличные от нейтральных; кривая
пишется, если она не тождественная (тогда же `ToneCurveName2012="Custom"`).

Таблица соответствия:

| ParamSet | crs-атрибут | Примечание |
|---|---|---|
| light.exposure/contrast/highlights/shadows/whites/blacks | `Exposure2012`, `Contrast2012`, `Highlights2012`, `Shadows2012`, `Whites2012`, `Blacks2012` | семантика 1:1, рендер отличается |
| white_balance.temp/tint | `IncrementalTemperature`, `IncrementalTint` + `WhiteBalance="Custom"` | только `target="rendered"`; для `raw` не пишется, в отчёт: «WB не переносится в RAW-пресет (LR хранит абсолютные K)» |
| presence.texture/clarity/dehaze/vibrance/saturation | `Texture`, `Clarity2012`, `Dehaze`, `Vibrance`, `Saturation` | 1:1 |
| tone_curve.master/red/green/blue | `ToneCurvePV2012`, `ToneCurvePV2012Red`, `ToneCurvePV2012Green`, `ToneCurvePV2012Blue` (rdf:Seq из `"x, y"`) | точки 1:1, интерполяция LR отличается |
| hsl.hue/saturation/luminance[color] | `HueAdjustment<Color>`, `SaturationAdjustment<Color>`, `LuminanceAdjustment<Color>`; Color ∈ Red, Orange, Yellow, Green, Aqua, Blue, Purple, Magenta | 1:1 |
| color_grading shadows/highlights hue, sat | `SplitToningShadowHue`, `SplitToningShadowSaturation`, `SplitToningHighlightHue`, `SplitToningHighlightSaturation` | |
| color_grading midtones / global | `ColorGradeMidtoneHue/Sat/Lum`, `ColorGradeGlobalHue/Sat/Lum` | |
| color_grading shadows.lum / highlights.lum | `ColorGradeShadowLum`, `ColorGradeHighlightLum` | |
| color_grading blending / balance | `ColorGradeBlending`, `SplitToningBalance` | |
| detail.sharpening | `Sharpness`, `SharpenRadius`, `SharpenDetail`, `SharpenEdgeMasking` | |
| detail.noise_reduction | `LuminanceSmoothing`, `LuminanceNoiseReductionDetail`, `LuminanceNoiseReductionContrast`, `ColorNoiseReduction`, `ColorNoiseReductionDetail`, `ColorNoiseReductionSmoothness` | |
| lens.distortion | `LensManualDistortionAmount` | |
| lens.vignetting / vignetting_midpoint | `VignetteAmount`, `VignetteMidpoint` | ручная коррекция объектива |
| lens.chromatic_aberration.remove | `AutoLateralCA="1"` | ручные red_cyan/blue_yellow не экспортируются (в отчёт) |
| transform.vertical/horizontal/rotate/aspect/scale/offset_x/offset_y | `PerspectiveVertical`, `PerspectiveHorizontal`, `PerspectiveRotate`, `PerspectiveAspect`, `PerspectiveScale`, `PerspectiveX`, `PerspectiveY` | только при `include_geometry=True` (специфично для кадра); иначе — в отчёт, если не нейтрально |
| transform.upright | — | не экспортируется; в отчёт: «включите Upright в LR вручную» |
| crop | `HasCrop="True"`, `CropTop`, `CropLeft`, `CropBottom`, `CropRight`, `CropAngle` | только при `include_geometry=True` |
| effects.vignette | `PostCropVignetteAmount`, `PostCropVignetteMidpoint`, `PostCropVignetteRoundness`, `PostCropVignetteFeather`, `PostCropVignetteHighlightContrast`, `PostCropVignetteStyle` (1 highlight_priority, 2 color_priority, 3 paint_overlay) | |
| effects.grain | `GrainAmount`, `GrainSize`, `GrainFrequency` (= roughness) | seed не переносится |
| local[] | — | **не экспортируются в MVP** (`MaskGroupBasedCorrections` сложен и зависит от версии LR); в отчёт — список имён пропущенных коррекций |

Для экспорта лука без фото `name` = `look.name`.

**Обязательная ручная проверка (не автотест):** импортировать
сгенерированный XMP хотя бы одного лука в Lightroom Classic или Camera Raw
и убедиться, что пресет открывается и ползунки выставлены. Имена атрибутов
сверить с пресетом, экспортированным из актуальной версии LR; при
расхождении — исправить таблицу в этом ТЗ и код. Результат проверки —
в описании PR.

### 2.12. Экспорт `.cube` LUT (`export_cube.py`)

`export_cube(params, title, size=33) -> tuple[str, list[str]]` — текст и
`mapping_report`.

- Вход/выход LUT — sRGB-кодированные значения [0,1] (display-referred).
- Решётка `size³`, R меняется быстрее всего, затем G, затем B (стандарт
  `.cube`). Заголовок: `TITLE "<title>"`, `LUT_3D_SIZE 33`,
  `DOMAIN_MIN 0.0 0.0 0.0`, `DOMAIN_MAX 1.0 1.0 1.0`. Значения — 6 знаков
  после точки, разделитель пробел.
- Генерация: решётка как изображение (size³ × 1 × 3) → EOTF → поточечные
  стадии с теми же функциями, что в `render`: WB, exposure, tone, tone
  curve, HSL, color grading, vibrance/saturation → OETF → клампинг [0,1].
- `mapping_report`: перечень непереносимых групп, отличных от нейтральных:
  NR, геометрия, коррекция объектива, dehaze, clarity, texture, local,
  шарпинг, виньетка, зерно.
- Если exposure > 0 или whites > 0 — строка в отчёт: значения выше 1.0
  в LUT клампятся.

### 2.13. Фаза 2 (НЕ реализовывать сейчас — только границы)

- **Генеративный режим** `creative_restyle(photo_id, prompt)` через OpenAI
  Images API; модель из `PHOTOGRADE_IMAGE_MODEL` (кандидаты
  `gpt-image-2.5-flare`, `gpt-image-2`); включается только при
  `PHOTOGRADE_ENABLE_GENERATIVE=1` и `OPENAI_API_KEY`; результат с суффиксом
  `_GENERATIVE` и полем `generative: true`; XMP/LUT для него не создаются.
  Параметры эндпоинта и цену сверить с документацией OpenAI в момент
  реализации.
- **ИИ-маски** (2.8.3).
- **HTTP-MCP для ChatGPT Apps** (публичный HTTPS, OAuth, передача файлов).
- Экспорт линейных/радиальных масок в XMP.

### 2.14. Документация

- `plugins/photograde/README.md`: установка
  (`pip install -e "plugins/photograde[raw]"`), подключение к Claude Code
  (`claude mcp add photograde -- photograde-mcp`) и пример `.mcp.json`,
  список инструментов, ограничения (0.2 п.4, 2.4.5, 2.9.2, 2.11, 2.12),
  env-переменные (`PHOTOGRADE_WORKDIR`, `PHOTOGRADE_PREVIEW_PX`,
  `PHOTOGRADE_MAX_MP`), примеры CLI.
- В конец корневого `README.md` — одна строка:
  `Плагин обработки фото Photograde — см. plugins/photograde/README.md.`

## 3. Ограничения и зависимости

- Python ≥ 3.11. Без scipy, scikit-image, torch, colour-science.
- Лицензии зависимостей: numpy (BSD), OpenCV 4.x (Apache-2.0), Pillow
  (MIT-CMU), pydantic (MIT), typer (MIT), mcp (MIT), rawpy (MIT; LibRaw —
  LGPL/CDDL).
- Никаких сетевых вызовов в MVP, никакой загрузки по URL (инструменты
  принимают только локальные пути).
- Пути: абсолютные или относительно cwd сервера; чтение только
  существующих файлов; запись — только в `out_dir` (по умолчанию
  `PHOTOGRADE_WORKDIR/exports`), `out_dir` создаётся при необходимости.
- Все операции детерминированы (зерно — через `seed`, k-means —
  `cv2.setRNGSeed(0)`).

## 4. Риски и цена

- **Деньги:** MVP — 0. Рассуждения и vision выполняет LLM хоста (подписка
  пользователя), сервер локальный, платных API нет. Фаза 2: генеративный
  режим — оплата за изображение по тарифу OpenAI (для 2.5 цена при
  подготовке ТЗ не проверена); ИИ-маски — 0 денег, но +150–400 МБ весов и
  1–5 с CPU на кадр; ChatGPT Apps — VPS с 2–4 ГБ RAM, HTTPS, OAuth.
- **Время (оценка):** MVP 7–10 рабочих дней. Разбивка на коммиты:
  (1) schema, color, io, стадии 3–5, 7–10 + тесты; (2) noise, geometry,
  presence, sharpen, effects; (3) masks + local; (4) analyze, match, looks,
  geometry_detect; (5) XMP + LUT; (6) session, MCP, CLI, AGENT_GUIDE,
  README, golden.
- **Ожидание «как в Lightroom 1:1»** — рендер отличается. Смягчение:
  оговорка в README и в ответе агента; XMP даёт пользователю «настоящий»
  LR-рендер.
- **Качество луков** — значения подобраны по описанию, не калиброваны по
  кадрам. Смягчение: `match_reference` по референсу пользователя, итерации
  агента по превью.
- **Перенос по статистике переносит содержание** — смягчено `strength` и
  ограничением наклонов.
- **Имена crs-атрибутов** могут отличаться в новых версиях LR —
  обязательная ручная проверка (2.11).
- **Память на больших файлах** — лимит `PHOTOGRADE_MAX_MP`.
- **ChatGPT как рантайм** — передача файлов в MCP/Actions там нестабильна;
  потребуется отдельное ТЗ на HTTP-обёртку, ядро к этому готово.

## 5. Критерии приёмки

- [ ] `pip install -e "plugins/photograde[dev]"` проходит; `ruff check plugins/photograde` без ошибок.
- [ ] Корневой `pytest -q` зелёный и не собирает тесты плагина; файлы вне `plugins/photograde/` не изменены, кроме одной строки в корневом README.
- [ ] `cd plugins/photograde && pytest -q` зелёный.
- [ ] `ParamSet` покрывает все группы 2.2 с указанными диапазонами и дефолтами; неизвестный ключ → ошибка с именем поля; выход за диапазон → клампинг + предупреждение.
- [ ] `render` с дефолтным ParamSet возвращает вход без изменений; после кодирования 8-битного входа — побитное совпадение.
- [ ] Порядок стадий соответствует таблице 2.4; нейтральная стадия не вычисляется.
- [ ] Превью и полный рендер согласованы (тест 6.2 п.16).
- [ ] Все 8 луков валидны; `find_look("твин пикс")` → `twin_peaks`.
- [ ] `match_reference(img, img)` даёт почти нейтральные параметры (допуски 6.3).
- [ ] `export_xmp` создаёт валидный XML; round-trip для всех экспортируемых полей; отчёт перечисляет непереносимое.
- [ ] `export_cube` создаёт файл с 33³ строками данных; LUT совпадает с `render` для поточечных параметров в пределах допуска 6.4.
- [ ] `photograde-mcp` стартует; все инструменты таблицы 2.7.2 зарегистрированы; `load_photo`, `apply_params`, `compare` возвращают изображение.
- [ ] CLI-команды 2.7.3 работают, коды возврата соответствуют.
- [ ] RAW без rawpy — понятная ошибка с подсказкой.
- [ ] Ручная проверка импорта XMP в LR/ACR выполнена, результат в описании PR.
- [ ] README плагина и `AGENT_GUIDE.md` написаны по 2.7.4 и 2.14.

## 6. Тесты

Команда: `cd plugins/photograde && pytest -q`. Зелёный прогон = 0 failed;
skipped допустимы только для RAW/HEIC без extras.

### 6.1. Синтетические входы (`conftest.py`, без бинарных фикстур)

- `gray_ramp(w=256, h=16)` — горизонтальный перцептивный градиент 0..1.
- `hue_patches()` — 8 патчей 32×32 HSV(центр полосы, S=0.8, V=0.8) +
  6 серых патчей (V = 0.05, 0.2, 0.4, 0.6, 0.8, 0.95); функция также
  возвращает координаты патчей.
- `checker(256, 192, cell=16)` — для геометрии.
- `tilted_lines(angle_deg)` — 512×384, 12 параллельных чёрных линий
  толщиной 2 px на белом, под углом.
- `converging_verticals(v)` — сетка вертикальных линий 512×384, искажённая
  гомографией vertical (2.4.2) с известным `v`.
- `noisy_flat(seed)` — поле 0.5 + гауссов шум sigma 0.05.
- `photo_like(seed)` — 192×128, сумма плавных цветных градиентов и
  гауссовых пятен, детерминированно от seed.
Все возвращают linear float32 (через EOTF).

### 6.2. Аналитические тесты (известный ответ)

1. Identity: `render(x, ParamSet()).image` == `x` (max abs ≤ 1e-6).
2. Exposure +1 → линейные значения ×2 (относительная ошибка ≤ 1e-5).
3. WB: серый патч сохраняет Y (|ΔY| ≤ 1e-4) при temp/tint ∈ {±50, ±100};
   temp > 0 → R растёт, B падает.
4. Монотонность тоновых функций: для whites/blacks/highlights/shadows/
   contrast ∈ {-100, -50, 50, 100} на 1024 точках [0,1] разности ≥ -1e-7.
5. Contrast +50: `f(0.25) < 0.25`, `f(0.75) > 0.75`, `|f(0.5) - 0.5| ≤ 1e-6`.
6. Кривая: тождественная → без изменений; `[[0,0],[128,64],[255,255]]` →
   128/255 переходит в 64/255 (±0.5/255); для монотонных точек результат
   монотонный и в [0,1].
7. HSL: `saturation.red = -100` → красный патч S ≤ 0.02, синий патч
   изменился ≤ 1/255; `hue.blue = +100` → hue синего патча +30° (±2°);
   серые патчи не меняются (≤ 1/255) при любых HSL.
8. Saturation -100 → R=G=B на всех пикселях (≤ 1e-6).
9. Color grading shadows {hue 200, sat 100}: серый патч V=0.2 получает
   b* < 0; изменение (a*, b*) патча V=0.95 по модулю в ≥ 5 раз меньше.
10. Виньетка amount -50: центральный пиксель изменён ≤ 1/255, угол темнее;
    amount +50 — угол светлее. Для каждого из трёх style.
11. Зерно: одинаковый seed → побитное совпадение; разный seed → различие;
    сдвиг среднего ≤ 0.01.
12. Геометрия: нейтральные параметры → identity; `checker`, повёрнутый
    rotate 5 → `detect_upright(level)` на результате ≈ -5 (±0.5);
    `tilted_lines(3)` → rotate ≈ -3 (±0.5); `converging_verticals(30)` →
    vertical ≈ -30 (±6); `constrain=True` при rotate 8 → нет чёрных
    пикселей в крайних строках/столбцах; scale 50 при constrain=True не
    падает; crop 0.25..0.75 по обеим осям → размер выхода вдвое меньше по
    каждой стороне (±1 px).
13. Дисторсия: при distortion 50 центральный пиксель неизменен, пиксели у
    края берутся ближе к центру (проверка на точке-метке), знак по 2.4.2.
14. NR: `noisy_flat` при luminance 80 → std уменьшается ≥ 2 раз, среднее
    сохраняется (±0.01).
15. Шарпинг: на ступеньке перепад на краю растёт; плоские области
    изменены ≤ 1/255.
16. Согласованность масштаба: `render(downscale(x, 0.5), p, scale=0.5)` vs
    `downscale(render(x, p, scale=1))` для `photo_like` и p с clarity 50,
    sharpening 60, NR 40 — средняя абсолютная разница ≤ 0.02; для зерна 30
    сравнивается std разности с исходником (±25%).
17. Маски: linear_gradient → 1 у start, 0 у end, 0.5 в середине (±0.02);
    radial inside/outside в сумме = 1; luminance_range выделяет нужные
    серые патчи (≥ 0.95) и не выделяет остальные (≤ 0.05) при feather 0;
    color_range(hue=240) — синий патч ≥ 0.95, красный ≤ 0.05;
    add/subtract/intersect/invert/opacity — по формулам на двух известных
    масках; local exposure +1 с `image`-маской (левая половина 255, правая
    0; файл создаётся в `tmp_path`) → изменилась только левая половина.
18. `normalize_params`: клампинг с предупреждениями нужного формата;
    ошибки на неизвестном ключе, дубликате x в кривой, `crop.left >= right`,
    `type="ai_sky"`, 17 локальных коррекциях.

### 6.3. Перенос стиля

- `match_reference(x, x)` для `photo_like(1)`: |temp|, |tint| ≤ 5; точки
  master-кривой в пределах ±3 от тождества; все `color_grading.*.sat` ≤ 5;
  |saturation| ≤ 5.
- `ref = render(x, {white_balance: {temp: 40}})`, strength=1,
  components=["wb"] → найденный temp ∈ [30, 50].
- `ref = render(x, {presence: {saturation: -50}})`, strength=1 →
  saturation < -20.
- Монохромный референс → `saturation == -100` и предупреждение.
- `ref = render(photo_like(2), look supernatural)`, src = `photo_like(1)` →
  `diagnostics.zone_ab_distance_after <= zone_ab_distance_before`.

### 6.4. Экспорт

- XMP: парсится `ElementTree`; есть `crs:PresetType="Normal"`, `crs:Name`,
  `crs:UUID` из 32 hex-символов; для лука `supernatural`
  `crs:Contrast2012="+25"`, `crs:Saturation="-25"`; round-trip
  `parse_xmp(export_xmp(p))` совпадает по всем экспортируемым полям для
  каждого из 8 луков; `target="raw"` → нет `IncrementalTemperature`, есть
  строка в отчёте; непустой `local` → строка в отчёте; геометрия без
  `include_geometry` не пишется.
- LUT: ровно 33³ строк данных, заголовок по 2.12; для identity значения
  совпадают с решёткой (≤ 1e-6); трилинейное применение LUT (реализовать
  в тесте) к `photo_like(3)` против `render` для лука `teal_orange` (все
  его параметры поточечные) — средний ΔE76 ≤ 1.5, максимальный ≤ 6;
  clarity ≠ 0 → строка в отчёте.

### 6.5. I/O

- JPEG: EXIF (тег Make, записанный в тесте) сохраняется; Orientation = 1
  на выходе; вход с Orientation = 6 поворачивается при загрузке.
- PNG с alpha → alpha побитно сохраняется в PNG; при выводе в JPEG —
  предупреждение.
- 16-бит TIFF round-trip — расхождение ≤ 1 LSB.
- `PHOTOGRADE_MAX_MP` = 0.01 (monkeypatch) → `ImageTooLargeError`.
- Обрезанный JPEG → `CorruptImageError`.
- RAW без rawpy (monkeypatch импорта) → `UnsupportedFormatError` с
  подсказкой. Тест чтения реального RAW выполняется, только если задан env
  `PHOTOGRADE_TEST_RAW` с путём к файлу и установлен rawpy; иначе skip.
- Существующий выходной файл не перезаписывается (суффикс `-1`).
- ICC: JPEG со встроенным sRGB-профилем (`ImageCms.createProfile("sRGB")`)
  → без предупреждения; ветка конвертации — через monkeypatch
  `_is_srgb_profile` → False: вызывается конвертация, в `warnings` есть
  строка `"converted from ... to sRGB"`, `icc_converted_from` заполнен.

### 6.6. Golden-тесты (`test_golden.py`)

- `tests/golden/cases.json`: 10 кейсов `{id, input: {generator, seed}, params | look_id}`:
  identity; каждый из 8 луков на `photo_like(7)`; один кейс с локальными
  масками (linear_gradient + color_range).
- Эталоны `tests/golden/<id>.npz` (uint16, 192×128) генерирует
  `python scripts/regen_golden.py --write`; без `--write` скрипт только
  печатает диффы. Эталоны коммитятся.
- Допуск: средняя абсолютная разница ≤ 0.002, максимальная ≤ 0.01
  (в нормированных [0,1]).
- Golden-тесты ловят регрессии, но не доказывают правильность (эталон
  создан тем же кодом); правильность проверяют 6.2–6.4. Перегенерация
  эталонов — только при осознанном изменении формул этого ТЗ, с причиной
  в сообщении коммита.

### 6.7. MCP и CLI

- Обработчики инструментов вызываются напрямую (без запуска процесса), с
  `PHOTOGRADE_WORKDIR` в `tmp_path`: `load_photo` → `apply_params`
  (частичный ParamSet) → `compare` → `export(formats=["jpeg","xmp","cube"])`;
  файлы существуют, ответы содержат ожидаемые ключи.
- `apply_params` с `light.exposure = 9` → предупреждение о клампинге;
  с ключом `light.exposur` → ошибка, в тексте есть `exposur`.
- `apply_params(look_id="nope")` → ошибка со списком доступных луков.
- Сервер регистрирует ровно инструменты таблицы 2.7.2 и prompt `grade_photo`
  (проверка через список инструментов объекта FastMCP).
- `typer.testing.CliRunner`: `schema`, `looks`, `apply --look twin_peaks --xmp --cube`,
  код 2 при невалидных параметрах.

### 6.8. Производительность (маркер `slow`)

- Превью 1600 px с луком `twin_peaks` ≤ 1.5 с; полный 24 Мп (синтетический)
  ≤ 20 с; результаты — в описание PR.
