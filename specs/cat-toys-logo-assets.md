# ТЗ: Логотип «Хулимяо» — вкрутить реальные ассеты (картинка + шрифт .otf)

Итерация 5. Заказчик загрузил в репо настоящие ассеты. Проверено Пупой:
- `landing/assets/logo.png.png` — картинка логотипа (пушистый серо-белый кот,
  прозрачный фон, 1254×1254). Имя задвоено по ошибке.
- `landing/assets/fonts/overdozesans.otf` — шрифт Overdoze Sans (266 КБ),
  **кириллица есть**, все буквы «ХУЛИМЯО» покрываются (проверено fontTools).

Файлы: `landing/index.html`, `landing/styles.css`, git-переименование.
Ветка `claude/pupa-lupa-agents-nw54ho`. Не ломать всё остальное; `pytest`
через `python -m pytest -q` зелёный.

## 1. Переименовать картинку

`git mv landing/assets/logo.png.png landing/assets/logo.png`
(убрать задвоенное расширение; в разметке ссылаемся на `assets/logo.png`).

## 2. @font-face под реальный файл .otf

В `landing/styles.css` поправить `@font-face` логотипа:
```css
@font-face {
  font-family: "Overdoze Sans";
  src: url("assets/fonts/overdozesans.otf") format("opentype");
  font-weight: 400 900;
  font-display: swap;
}
```
- Имя файла — `overdozesans.otf` (как загружено), формат — `opentype`.
- Фолбэк-стек `.logo-word` не трогать (останется как страховка).
- Обновить README в `assets/fonts/` — отметить, что файл на месте
  (`overdozesans.otf`), TODO снять.

## 3. Заменить SVG-кота на картинку-логотип

В `landing/index.html` внутри `<a class="logo">` **заменить весь inline-SVG
`.logo-mark`** на изображение:
```html
<img class="logo-mark" src="assets/logo.png"
     alt="Хулимяо — пушистый кот" width="240" height="240">
```
- Картинка квадратная (1254×1254), но кот в ней — лежит горизонтально, сверху
  и снизу прозрачные поля. Поэтому в CSS показывать по ШИРИНЕ, высоту авто:
  ```css
  .logo-mark { display: block; width: clamp(160px, 40vw, 240px); height: auto; }
  ```
  (крупный бренд-визуал над названием; на мобиле ≤360px влезает).
- Лок-ап (`<a class="logo" href="#top">` + `<h1>`) остаётся кликабельным.
- `alt` осмысленный. Знак декоративный по сути, но альт с названием ок.
- Слой курсора (`pointer-events:none`) не задет; картинка не мешает клику по
  логотипу.

## 4. Не трогать
Логотип-текст `.logo-word` (размер/объём/цвет из прошлой итерации),
анимацию котёнка-курсора, подсветку кнопок, фолбэки, Commissioner, адаптив,
Python.

## 5. Критерии приёмки
- [ ] Картинка переименована в `assets/logo.png` (git mv, история сохранена).
- [ ] Над названием — `<img>` с этой картинкой, крупная, по центру, ширина
      по `clamp`, высота авто; на ≤360px не ломает вёрстку.
- [ ] Старый inline-SVG кота удалён из разметки.
- [ ] `@font-face` ссылается на `assets/fonts/overdozesans.otf`
      `format("opentype")`; название «ХУЛИМЯО» рендерится Overdoze (кириллица
      есть). Фолбэк-стек сохранён.
- [ ] Лок-ап кликабелен; клики/курсор-фича не сломаны.
- [ ] `python -m pytest -q` зелёный; `node --check script.js` ок; консоль чистая.
- [ ] Саморевью `code-review` пройдено, находки разобраны.
