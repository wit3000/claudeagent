# Шрифты логотипа

Файл на месте: `overdozesans.otf` (Overdoze Sans, кириллица есть, все буквы
«ХУЛИМЯО» покрываются). TODO снят.

Логотип «Хулимяо» подключает Overdoze Sans через `@font-face` в
`landing/styles.css` (самохостинг, путь `assets/fonts/overdozesans.otf`,
формат `opentype`).

Кириллический фолбэк из `.logo-word`
(`"Onest", "Arial Black", sans-serif`, вес 800) остаётся как
страховка — если веб-шрифт не загрузится, название останется жирным и
читаемым.
