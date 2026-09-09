/* ============================================================
   Хулимяо — логика лендинга
   Состояние, координаты курсора, машина состояний MOVING/IDLE,
   покадровое движение (rAF) и переключение CSS-классов, наполнение
   таблицы цен, фолбэки. Оформление классов живёт в styles.css.
   ============================================================ */
(function () {
  "use strict";

  /* ----------------------------------------------------------
     КОНФИГ ФИШКИ (единственное место для правки параметров)
     ---------------------------------------------------------- */
  var CONFIG = {
    IDLE_MS: 400,       // порог простоя курсора → котёнок прыгает и садится
    CHASE_EASE: 0.15,   // коэффициент погони котёнка за точкой (lerp)
    JUMP_MS: 300,       // длительность прыжка (синхронно с CSS @keyframes)
    DOT_SIZE: 14,       // px (для справки; вид задаётся в CSS)
    CAT_SIZE: 60,       // px (для справки; вид задаётся в CSS)
    Z_INDEX: 9999,      // (для справки; z-index задаётся в CSS)
    FLIP_DEADZONE: 2    // px, чтобы флип не дёргался у нуля
  };

  /* ----------------------------------------------------------
     ДАННЫЕ КЛИЕНТА
     TODO: подтвердить — контакты и цены рандомные плейсхолдеры.
     ---------------------------------------------------------- */
  var CONTACTS = {
    // TODO: подтвердить
    phone: "+79161234567",
    // TODO: подтвердить
    whatsapp: "https://wa.me/79161234567",
    // TODO: подтвердить
    telegram: "https://t.me/hulimyao",
    // Префилл-текст для WhatsApp (URL-encoded).
    waText: "Здравствуйте! Интересуют игрушки для кошки"
  };

  // TODO: подтвердить — цены указаны для примера.
  var PRICES = [
    { item: "Удочка-дразнилка",       ours: 490,  offline: 790 },
    { item: "Пирамидка",              ours: 690,  offline: 1090 },
    { item: "Когтеточка",             ours: 1290, offline: 1990 },
    { item: "Мышка (набор 3 шт.)",    ours: 350,  offline: 590 },
    { item: "Автоматическая игрушка", ours: 1990, offline: 2890 }
  ];

  /* ----------------------------------------------------------
     ГОД В ФУТЕРЕ
     ---------------------------------------------------------- */
  function setYear() {
    var el = document.getElementById("footer-year");
    if (el) el.textContent = String(new Date().getFullYear());
  }

  /* ----------------------------------------------------------
     СИНХРОНИЗАЦИЯ ССЫЛОК ИЗ CONTACTS (единый источник данных)
     Базовые href есть в HTML; здесь приводим их к значениям конфига.
     ---------------------------------------------------------- */
  function applyContacts() {
    var waHref = CONTACTS.whatsapp;
    if (CONTACTS.waText) {
      waHref += "?text=" + encodeURIComponent(CONTACTS.waText);
    }
    var map = {
      phone: "tel:" + CONTACTS.phone,
      whatsapp: waHref,
      telegram: CONTACTS.telegram
    };
    var nodes = document.querySelectorAll("[data-contact]");
    for (var i = 0; i < nodes.length; i++) {
      var kind = nodes[i].getAttribute("data-contact");
      if (map[kind]) nodes[i].setAttribute("href", map[kind]);
    }
  }

  /* ----------------------------------------------------------
     НАПОЛНЕНИЕ ТАБЛИЦЫ ЦЕН (расчёт экономии из чисел)
     ---------------------------------------------------------- */
  function renderPrices() {
    var body = document.getElementById("price-body");
    if (!body) return;
    var fmt = new Intl.NumberFormat("ru-RU");
    var rows = "";
    for (var i = 0; i < PRICES.length; i++) {
      var p = PRICES[i];
      var saveRub = p.offline - p.ours;
      var savePct = Math.round((p.offline - p.ours) / p.offline * 100);
      rows +=
        "<tr>" +
          "<td>" + escapeHtml(p.item) + "</td>" +
          "<td class=\"col-ours\">" + fmt.format(p.ours) + " ₽</td>" +
          "<td class=\"col-offline\">" + fmt.format(p.offline) + " ₽</td>" +
          "<td><span class=\"price-badge\">−" + savePct + "%&nbsp;/&nbsp;−" +
            fmt.format(saveRub) + " ₽</span></td>" +
        "</tr>";
    }
    body.innerHTML = rows;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  /* ----------------------------------------------------------
     ФИШКА КУРСОРА: лазерная точка + котёнок
     ---------------------------------------------------------- */
  function initCursorFx() {
    // Фолбэк 1: только точный указатель (десктоп). На touch/мобиле — выходим.
    var finePointer = window.matchMedia &&
      window.matchMedia("(pointer: fine)").matches;
    if (!finePointer) return;

    // Решение по prefers-reduced-motion: фичу НЕ выключаем целиком (точка
    // по-прежнему помогает целиться), но делаем котёнка статичным — он
    // мгновенно «прилипает» к точке без погони и без дуги прыжка (chaseEase=1),
    // а декоративные @keyframes бега/прыжка/пульсации/idle глушит медиазапрос
    // в styles.css. Вариант «убрать анимации бега/прыжка» из п. 2.5 ТЗ.
    var reduceMotion = window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var chaseEase = reduceMotion ? 1 : CONFIG.CHASE_EASE;

    var dot = document.getElementById("laser-dot");
    var cat = document.getElementById("cat");
    if (!dot || !cat) return;

    // Прокидываем JUMP_MS в CSS-переменную, чтобы длительности совпадали.
    cat.style.setProperty("--jump-ms", CONFIG.JUMP_MS + "ms");

    // Активируем фичу: скрываем нативный курсор, показываем слой.
    document.body.classList.add("cursor-fx");

    var STATE = { MOVING: "MOVING", IDLE: "IDLE" };
    var state = STATE.IDLE;

    var pointerX = window.innerWidth / 2;
    var pointerY = window.innerHeight / 2;
    var catX = pointerX;
    var catY = pointerY;
    var lastMoveTs = 0;
    var jumpTimer = null;
    var facingLeft = false;
    var visible = true;
    var rafId = null;
    var hotEl = null; // текущий подсвеченный лазером элемент (a/button)

    function setClass(name, on) {
      cat.classList.toggle(name, on);
    }

    function enterMoving() {
      if (state === STATE.MOVING) return;
      state = STATE.MOVING;
      if (jumpTimer) { clearTimeout(jumpTimer); jumpTimer = null; }
      setClass("cat--jumping", false);
      setClass("cat--sitting", false);
      setClass("cat--running", true);
      dot.classList.remove("dot--caught"); // точка снова «горит»
    }

    function enterIdle() {
      state = STATE.IDLE;
      setClass("cat--running", false);
      // Котёнок допрыгивает точно на точку.
      catX = pointerX;
      catY = pointerY;
      writeCat();
      if (reduceMotion) {
        // Без дуги прыжка — сразу садится и накрывает точку.
        setClass("cat--sitting", true);
        dot.classList.add("dot--caught");
        return;
      }
      setClass("cat--jumping", true);
      jumpTimer = setTimeout(function () {
        setClass("cat--jumping", false);
        setClass("cat--sitting", true);
        dot.classList.add("dot--caught"); // точка «поймана» под лапами
        jumpTimer = null;
      }, CONFIG.JUMP_MS);
    }

    function writeDot() {
      dot.style.transform =
        "translate3d(" + pointerX + "px," + pointerY + "px,0)";
    }
    function writeCat() {
      cat.style.transform =
        "translate3d(" + catX + "px," + catY + "px,0)";
    }

    function loop() {
      var now = performance.now();
      writeDot();

      if (state === STATE.MOVING) {
        // Погоня с задержкой (lerp). При reduced-motion chaseEase=1 → мгновенно.
        var dx = pointerX - catX;
        var dy = pointerY - catY;
        catX += dx * chaseEase;
        catY += dy * chaseEase;
        writeCat();

        // Флип по направлению (с мёртвой зоной, чтобы не дёргался).
        if (dx < -CONFIG.FLIP_DEADZONE && !facingLeft) {
          facingLeft = true; setClass("cat--flip", true);
        } else if (dx > CONFIG.FLIP_DEADZONE && facingLeft) {
          facingLeft = false; setClass("cat--flip", false);
        }

        // Переход в IDLE по простою.
        if (now - lastMoveTs > CONFIG.IDLE_MS) {
          enterIdle();
        }
        rafId = requestAnimationFrame(loop);
      } else {
        // IDLE: enterIdle() уже посадил котёнка точно на точку — доигрывать
        // нечего, не гоняем rAF вхолостую до следующего mousemove.
        rafId = null;
      }
    }

    function ensureLoop() {
      if (rafId === null) rafId = requestAnimationFrame(loop);
    }

    /* --- Слушатели --- */
    function onMove(e) {
      pointerX = e.clientX;
      pointerY = e.clientY;
      lastMoveTs = performance.now();
      if (!visible) return; // не будим при спрятанном курсоре
      enterMoving();
      ensureLoop();
    }

    function onLeave() {
      visible = false;
      dot.style.visibility = "hidden";
      cat.style.visibility = "hidden";
      setHot(null); // курсор ушёл за окно — снимаем подсветку кнопки
    }
    function onEnter(e) {
      visible = true;
      dot.style.visibility = "";
      cat.style.visibility = "";
      pointerX = e.clientX;
      pointerY = e.clientY;
      lastMoveTs = performance.now();
      enterMoving();
      ensureLoop();
    }

    // Над кликабельным: точка крупнее + сама кнопка/ссылка подсвечивается.
    // hotEl хранит текущий подсвеченный элемент; вешаем/снимаем класс на нём.
    function setHot(el) {
      if (hotEl === el) return;
      if (hotEl) hotEl.classList.remove("laser-hot");
      hotEl = el;
      if (hotEl) hotEl.classList.add("laser-hot");
      dot.classList.toggle("dot--hot", !!hotEl);
    }
    function onOver(e) {
      var t = e.target.closest && e.target.closest("a,button");
      if (t) setHot(t);
    }
    function onOut(e) {
      if (!e.target.closest || !e.target.closest("a,button")) return;
      // Снимаем только если уходим не на другой кликабельный (onOver наведёт
      // подсветку на новый элемент сам — без мигания).
      var to = e.relatedTarget;
      if (!to || !to.closest || !to.closest("a,button")) {
        setHot(null);
      }
    }

    document.addEventListener("mousemove", onMove, { passive: true });
    // mouseleave/enter вешаем на documentElement — надёжнее ловит уход курсора
    // за пределы окна, чем document, в части браузеров.
    document.documentElement.addEventListener("mouseleave", onLeave);
    document.documentElement.addEventListener("mouseenter", onEnter);
    document.addEventListener("mouseover", onOver, { passive: true });
    document.addEventListener("mouseout", onOut, { passive: true });

    // Стартовое состояние: сидит по центру, ждёт движения.
    writeDot();
    writeCat();
    setClass("cat--sitting", true);
    dot.classList.add("dot--caught");
  }

  /* ----------------------------------------------------------
     СТАРТ
     ---------------------------------------------------------- */
  function init() {
    setYear();
    applyContacts();
    renderPrices();
    initCursorFx();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
