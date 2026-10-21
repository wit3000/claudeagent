#!/usr/bin/env python3
"""Mechanical style check of a Russian Markdown article.

Usage:
    python3 scripts/lint_text.py article.md
    python3 scripts/lint_text.py article.md --json
    cat article.md | python3 scripts/lint_text.py -

Finds what can be found without understanding the text: stop-list phrases,
words from the wrong register, slang, actions without a named actor ("берут",
"выбирают"), choppy runs of short sentences, paragraphs without links between
sentences, repeated words and roots, template cards, too many "the manufacturer
claims" disclaimers and typography errors. Cohesion and word
choice still need a slow human-style reading; this script only makes sure the
obvious things are not missed.

Findings have two levels: "error" must be fixed, "warn" must be looked at and
either fixed or consciously kept. The "## Заметки к сдаче" block is skipped.
Exit code: 0 without errors, 1 if there are errors, 2 if the file cannot be read.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from text_stats import (  # noqa: E402
    FENCE_RE,
    HEADING_RE,
    HR_RE,
    LIST_ITEM_RE,
    clean_inline,
    count_words,
    is_table_row,
    split_sentences,
    strip_notes,
)

MARKER_RE = re.compile(r"\[(?:нужны данные|не проверено):[^\]]*\]")
CYRILLIC_RE = re.compile(r"[а-яё]", re.IGNORECASE)
WORD_RE = re.compile(r"[а-яёa-z0-9]+(?:-[а-яёa-z0-9]+)*", re.IGNORECASE)

# (regex, hint). Every entry is a "запрет" from the shared stop-list or plain канцелярит.
STOP_PATTERNS: list[tuple[str, str]] = [
    (r"в современном мире", "пустой зачин — начни с сути"),
    (r"в наше время", "пустой зачин"),
    (r"на сегодняшний день", "«сейчас» или дата"),
    (r"ни для кого не секрет", "удали зачин, оставь факт"),
    (r"давайте (разбер|посмотр|рассмотр|погрузи|поговор)\w*", "сразу разбирай, без приглашения"),
    (r"в этой статье (мы )?(расскаж|рассмотр|разбер)\w*", "анонс вместо ответа"),
    (r"погрузимся", "калька с dive into"),
    (r"откройте для себя", "рекламная калька"),
    (r"вы когда-нибудь задумывались", "риторический заход"),
    (r"многие задаются вопросом", "выдуманный массовый интерес"),
    (r"как вы, наверное, знаете", "удали"),
    (r"добро пожаловать в мир", "рекламное обрамление"),
    (r"актуальн\w* как никогда", "оценка без доказательства"),
    (r"(важно|стоит|следует) (отметить|подчеркнуть|упомянуть)", "объяви не важность, а саму мысль"),
    (r"стоит (учитывать|помнить)|не стоит забывать", "напоминание вместо информации"),
    (r"игра\w* (ключев|важн|значим|решающ)\w* роль", "назови действие"),
    (r"неотъемлем\w*", "канцелярит и пафос"),
    (r"ключев\w* (фактор|момент|аспект)\w*", "не объясняет, чем ключевой"),
    (r"немаловажн\w*", "вялая оценка"),
    (r"особое внимание (стоит|следует|нужно) уделить", "указание вместо содержания"),
    (r"секрет прост|ответ прост", "обещание тайны"),
    (r"не просто [^.,;:!?]{1,40}, а ", "конструкция «не просто X, а Y»"),
    (r"подводя итог|в заключение", "финал-пересказ"),
    (r"широк\w* (спектр|ассортимент|выбор)", "перечисли, что именно"),
    (r"богат\w* ассортимент", "число или состав"),
    (r"индивидуальн\w* подход", "что именно подстраивается"),
    (r"команд\w* профессионалов", "самооценка без фактов"),
    (r"в кратчайшие сроки", "назови срок"),
    (r"по доступн\w* цен\w*", "назови цену"),
    (r"на высшем уровне", "удали или факт"),
    (r"динамично развивающ\w*", "штамп пресс-релиза"),
    (r"идеальн\w* (решени|выбор|вариант)\w*", "скажи, для чего подходит"),
    (r"выгодн\w* услови\w*", "назови условие"),
    (r"комплексн\w* решени\w*", "перечисли, что входит"),
    (r"мы рады предложить", "калька"),
    (r"осуществл\w*|осуществи\w*", "пустой глагол — замени глаголом действия"),
    (r"\bявля(ется|ются|лся|лась|лись)\b", "связка-канцелярит: тире или глагол"),
    (r"\bданн(ый|ая|ое|ого|ой|ому|ую)\b", "«этот»"),
    (r"в целях|с целью", "«чтобы», «для»"),
    (r"в связи с тем,? что", "«потому что»"),
    (r"посредством", "канцелярит"),
    (r"в случае,? если", "«если»"),
    (r"имеет место", "«бывает», «есть»"),
    (r"в процессе\b", "обычно лишнее: «в пути», «при…»"),
    (r"на предмет\b", "«проверить, нет ли…»"),
    (r"вышеуказанн\w*|нижеперечисленн\w*|вышеперечисленн\w*", "язык служебной записки"),
    (r"в рамках\b", "«по», «в»"),
    (r"(оказани|предоставлени)\w* услуг", "назови действие"),
    (r"в обязательном порядке", "«обязательно»"),
    (r"в настоящее время", "«сейчас» или удали"),
    (r"по истечении", "«после», «через»"),
    (r"при наличии", "«если есть»"),
    (r"денежн\w* средств\w*", "«деньги», «оплата»"),
    (r"как известно", "кому известно?"),
    (r"золот\w* середин\w*", "затёртая метафора"),
    (r"не стоит на месте|не стоят на месте", "пустая фраза"),
    (r"как говорится", "подводка к банальности"),
    (r"по праву (считается|является)", "кем считается?"),
    (r"предоставля\w* возможност\w*", "«можно»"),
    (r"на (ежедневной|регулярной|постоянной) основе", "калька"),
    (r"\bнаша экспертиза\b", "по-русски «экспертиза» — не «опыт»"),
    (r"и это нормально", "калька"),
    (r"мы всегда рады помочь", "вежливость без информации"),
    (r"существует множество", "назови число и что именно"),
    (r"каждый случай индивидуален", "отговорка — назови, от чего зависит"),
    (r"\bкак видите\b", "удали"),
    (r"формул\w* безопасн\w*", "калька с этикетки: «подходит для…»"),
    (r"вед[её]т себя на", "калька: «подходит ли»"),
    (r"закрыва\w* (задач|потребност|вопрос|запрос|бол[ьи])\w*", "машинный жаргон — «подходит для», «справляется с», «хватает для»"),
    (r"закры(ть|л|ла|ли) (задач|потребност|вопрос|запрос|бол[ьи])\w*", "машинный жаргон — «подходит для», «справляется с»"),
    (r"под (вашу|свою|любую|любые|ваши|свои|конкретную|конкретные) задач\w*", "абстракция — слова из мира темы: «под свой дом и бюджет»"),
    (r"(полн|широк)\w* спектр\w*", "перечисли, что именно"),
    (r"оптимальн\w* (решени|выбор|вариант)\w*", "оптимальный по какому параметру? назови его"),
    (r"заслужива\w* (особого )?внимани\w*", "скажи, чем именно интересно"),
    (r"отдельно стоит (рассмотреть|сказать|упомянуть)", "сразу содержание"),
    (r"(звучит )?знакомо\?", "риторический крючок — опиши ситуацию"),
    (r"\bпризнайтесь\b|\bсогласитесь\b", "фальшивая задушевность"),
    (r"\bспойлер\b", "фальшивая задушевность"),
    (r"(это )?не магия|никакой магии", "штамп «не X, а Y» — скажи, как это устроено"),
    (r"главн\w* секрет|правило (одно|простое)|вот (что|в ч[её]м) (важно|фишка|секрет)", "псевдооткрытие — сразу конкретика"),
    (r"\bфишк\w*", "жаргон — «особенность», «удачная деталь» или конкретика"),
    (r"\bтопов\w*", "жаргон — «лучший в подборке» с основанием"),
    (r"\bбомбическ\w*|\bкайф\w*", "жаргон"),
    (r"\bзамороч\w*|не парьтесь", "просторечие — «не придётся…»"),
    (r"\bлайфхак\w*", "жаргон — «совет», «приём»"),
    (r"\bюза(ть|ют|ет|ем)\b", "жаргон"),
]

# Colloquialisms that are sometimes fine ("путь короче", "реально ли"): look, don't auto-fix.
SLANG_PATTERNS: list[tuple[str, str]] = [
    (r"(^|[.!?…]\s+)короче,", "просторечие в начале фразы"),
    (r"\bреально (крут|классн|удобн|помога|работа|хорош)\w*", "«реально» как усилитель — убери или дай факт"),
    (r"\bзаш(ло|ла|ли|[её]л)\b", "просторечие — «понравился» с основанием"),
    (r"\bогонь\b", "просторечие, если не о пламени"),
    (r"\bсупер\b|\bвау\b", "просторечие"),
    (r"\bдержите\b|\bловите\b", "фамильярное обращение"),
]

# Words that usually come from the wrong register in consumer topics
# (beauty, health, home, hobby, travel). Warnings, not errors: in B2B texts
# some of them are fine.
REGISTER_PATTERNS: list[tuple[str, str]] = [
    (r"\bзадач(а|и|е|у|ей|ам|ами|ах)?\b", "«задача» — слово менеджмента; в потребительской теме: «если волосы…», «что вам нужно»"),
    (r"\bрешени(е|я|ю|ем)\b", "«решение» часто калька с solution — назови средство или что оно делает"),
    (r"\bприменени\w*|\bиспользовани\w*", "отглагольное существительное — замени глаголом"),
    (r"\bрассчитан(а|о|ы)? на\b", "техническая лексика — «подойдёт», «берут для…»"),
    (r"\bфункционал\w*", "жаргон"),
    (r"\bэффективн\w*", "без меры эффекта — пустая оценка"),
    (r"\bоптимальн\w*", "оптимальный по какому параметру?"),
    (r"\bпозволя(ет|ют)\b", "часто лишнее: «X позволяет сделать Y» → «с X можно Y»"),
    (r"\bобеспечива(ет|ют)\b", "канцелярский глагол — назови действие"),
    (r"\bпроизвод(ит|ят)ся\b", "пассив-канцелярит"),
    (r"\bэффект(ом|а|у)?\b", "размытое слово — скажи, что происходит"),
    (r"\bработа(ет|ют)\b", "о веществах и средствах так не говорят — скажи, что именно делает"),
    (r"\bудобн\w*", "«удобно» — только о физическом комфорте; иначе «проще», «быстрее», «ближе» или причина"),
    (r"\bзакрыва\w*", "«закрывать» — только в прямом смысле: дверь, заслонка, контур"),
]

# 3rd person plural verbs that hide who acts: "такие модели берут для дачи".
IMPERSONAL_RE = re.compile(
    r"\b(берут|покупают|приобретают|заказывают|используют|применяют|выбирают|предпочитают|ценят"
    r"|любят|ставят|устанавливают|советуют|рекомендуют|хвалят|отмечают|держат|ищут)\b",
    re.IGNORECASE,
)
# Who may act: pronouns and animate nouns (agent suffixes or a short list of people).
ACTOR_RE = re.compile(
    r"\b(они|мы|кто|те|оба|обе|семьи|дети|люди|мамы|родители|мастера|врачи|хозяйки|новички|профессионалы"
    r"|[а-яё]+(?:тели|ники|щики|чики|исты|еры|ёры|анты|енты|цы|ане|яне|логи|ологи))\b",
    re.IGNORECASE,
)
VAGUE_ACTOR_RE = re.compile(r"\b(многие|большинство|люди|вс[её] чаще|вс[её] больше людей)\b", re.IGNORECASE)
REASON_RE = re.compile(r"потому что|так как|из-за|благодаря|чтобы|\bза\b|\bесли\b|\bкогда\b|[:—]", re.IGNORECASE)

ATTRIBUTION_RE = re.compile(
    r"производител\w* (заявля|обеща|утвержда|указыва|рекоменду|сообща|пиш)\w*"
    r"|по (данным|описанию|словам|отзывам|информации|заявлению)\b"
    r"|(как )?заявля\w* производител\w*",
    re.IGNORECASE,
)

CONNECTOR_RE = re.compile(
    r"\b(поэтому|потому|так как|так что|но|а|однако|зато|если|когда|чтобы|например|ведь|тогда"
    r"|значит|при этом|хотя|иначе|тоже|также|ещё|кроме того|в отличие|из-за|благодаря|то есть"
    r"|этот|эта|это|эти|этого|этой|этим|этих|такой|такая|такое|такие|таким|таких|он|она|оно|они"
    r"|его|её|их|ему|ей|им|ним|ней|нему|него|там|здесь|сначала|затем|потом|после|причём|правда"
    r"|даже|только|зато|впрочем|наоборот|итак|кстати|скажем|например|в итоге|в результате)\b",
    re.IGNORECASE,
)

POLITE_RE = re.compile(r"\b(?:Вы|Вас|Вам|Ваш\w*|Вами)\b")
LABEL_RE = re.compile(r"^\s*(?:[-*+]\s+)?\**([А-ЯЁA-Z][^:*]{1,40}?)\**:\**\s")

# Pronouns and other function words repeat by nature.
FUNCTION_STEMS = {"которы", "которо", "котору", "сейчас", "только", "больше", "меньше", "несмот"}

SHORT_SENTENCE_WORDS = 9
CHOPPY_RUN = 4
LONG_SENTENCE_WORDS = 25
SHINGLE = 6


@dataclass
class Finding:
    level: str
    category: str
    line: int
    quote: str
    hint: str


@dataclass
class Block:
    kind: str  # heading, paragraph, item, table
    line: int
    text: str
    level: int = 0  # heading level


def parse_blocks(text: str) -> list[Block]:
    lines = strip_notes(text.lstrip("﻿").splitlines())
    blocks: list[Block] = []
    paragraph: list[str] = []
    para_line = 0
    fence = ""

    def flush() -> None:
        if paragraph:
            blocks.append(Block("paragraph", para_line, " ".join(paragraph)))
            paragraph.clear()

    for number, raw in enumerate(lines, start=1):
        line = raw.rstrip()
        fence_match = FENCE_RE.match(line)
        if fence:
            if fence_match and fence_match.group(1) == fence:
                fence = ""
            continue
        if fence_match:
            flush()
            fence = fence_match.group(1)
            continue
        if not line.strip() or HR_RE.match(line):
            flush()
            continue
        heading = HEADING_RE.match(line)
        if heading:
            flush()
            blocks.append(Block("heading", number, heading.group(2), len(heading.group(1))))
            continue
        if is_table_row(line):
            flush()
            blocks.append(Block("table", number, line))
            continue
        item = LIST_ITEM_RE.match(line)
        if item:
            flush()
            blocks.append(Block("item", number, item.group(1)))
            continue
        if line.lstrip().startswith(">"):
            line = line.lstrip()[1:]
        if not paragraph:
            para_line = number
        paragraph.append(line.strip())
    flush()
    return blocks


def plain(text: str) -> str:
    return MARKER_RE.sub("", clean_inline(text))


def words(text: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(text)]


def short_quote(text: str, limit: int = 120) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def check_patterns(blocks, findings):
    compiled_stop = [(re.compile(p, re.IGNORECASE), h) for p, h in STOP_PATTERNS]
    compiled_reg = [(re.compile(p, re.IGNORECASE), h) for p, h in REGISTER_PATTERNS]
    compiled_slang = [(re.compile(p, re.IGNORECASE), h) for p, h in SLANG_PATTERNS]
    for block in blocks:
        text = plain(block.text)
        for regex, hint in compiled_slang:
            for match in regex.finditer(text):
                findings.append(Finding("warn", "просторечие", block.line, match.group(0).strip(" .!?…"), hint))
        spans = []
        for regex, hint in compiled_stop:
            for match in regex.finditer(text):
                spans.append(match.span())
                findings.append(Finding("error", "стоп-лист", block.line, match.group(0), hint))
        for regex, hint in compiled_reg:
            for match in regex.finditer(text):
                if any(a <= match.start() < b for a, b in spans):
                    continue  # already an error
                findings.append(Finding("warn", "слово не из темы", block.line, match.group(0), hint))


def check_typography(blocks, findings):
    rules = [
        (re.compile(r'"'), "error", "прямые кавычки — нужны «ёлочки»"),
        (re.compile(r"\s-\s"), "error", "дефис вместо тире — «—» с пробелами"),
        (re.compile(r"(?<![\w.])\d+-\d+(?![\w.-])"), "error", "диапазон через дефис — «–» без пробелов"),
        (re.compile(r"(?<![\w.])\d+\.\d+(?!\.\d)(?!\w)"), "warn", "дробь через точку — в русском тексте запятая"),
        (re.compile(r"\bруб\b\.?"), "error", "«₽»"),
        (re.compile(r"\bм[23]\b"), "error", "«м²», «м³»"),
        (re.compile(r"\.\.\."), "warn", "многоточие — «…»"),
        (re.compile(r"!"), "warn", "восклицательный знак"),
    ]
    for block in blocks:
        if block.kind == "table":
            text = block.text
        else:
            text = MARKER_RE.sub("", re.sub(r"\]\([^)]*\)", "]", block.text))
        for regex, level, hint in rules:
            for match in regex.finditer(text):
                findings.append(Finding(level, "типографика", block.line, match.group(0), hint))
        if block.kind == "table":
            continue
        for sentence in split_sentences(plain(block.text)):
            for match in POLITE_RE.finditer(sentence.strip()):
                if match.start() == 0:
                    continue
                findings.append(Finding("error", "типографика", block.line, match.group(0),
                                        "«вы» со строчной в середине предложения"))


def sentences_of(blocks):
    for block in blocks:
        if block.kind in ("paragraph", "item"):
            yield block, split_sentences(plain(block.text))


def check_sentences(blocks, findings):
    for block, sentences in sentences_of(blocks):
        lengths = [count_words(s) for s in sentences]
        for sentence, length in zip(sentences, lengths):
            if length > LONG_SENTENCE_WORDS:
                findings.append(Finding("warn", "длинное предложение", block.line, short_quote(sentence),
                                        f"{length} слов — раздели, если в нём больше одной мысли"))
        if block.kind != "paragraph":
            continue
        run = 0
        for i, length in enumerate(lengths):
            # A short sentence tied to the previous one by a connector reads fine.
            unlinked = i == 0 or not CONNECTOR_RE.search(sentences[i])
            run = run + 1 if length <= SHORT_SENTENCE_WORDS and unlinked else 0
            if run == CHOPPY_RUN:
                findings.append(Finding("warn", "рубленый ритм", block.line,
                                        short_quote(" ".join(sentences[i - CHOPPY_RUN + 1:i + 1])),
                                        f"{CHOPPY_RUN} коротких несвязанных предложения подряд — свяжи их"))
        if len(sentences) >= 4:
            linked = sum(1 for s in sentences[1:] if CONNECTOR_RE.search(s))
            if linked * 2 < len(sentences) - 1:
                findings.append(Finding("warn", "нет связок", block.line, short_quote(block.text),
                                        "предложения стоят рядом, но не связаны: причина, пример, уточнение?"))
        firsts = [words(s)[:1] for s in sentences]
        for i in range(1, len(firsts)):
            if firsts[i] and firsts[i] == firsts[i - 1]:
                findings.append(Finding("warn", "одинаковое начало", block.line, short_quote(sentences[i]),
                                        f"два предложения подряд начинаются с «{firsts[i][0]}»"))


def check_attribution(blocks, findings):
    section_line, count, quotes = 0, 0, []

    def flush():
        if count > 1:
            findings.append(Finding("warn", "оговорки", section_line, "; ".join(quotes),
                                    f"{count} оговорки в одном разделе — оставь одну там, где обещание спорное"))

    for block in blocks:
        if block.kind == "heading":
            flush()
            section_line, count, quotes = block.line, 0, []
            continue
        for match in ATTRIBUTION_RE.finditer(plain(block.text)):
            count += 1
            quotes.append(match.group(0))
    flush()


def check_templates(blocks, findings):
    labels: dict[str, list[int]] = defaultdict(list)
    for block in blocks:
        if block.kind in ("paragraph", "item"):
            match = LABEL_RE.match(block.text)
            if match:
                labels[match.group(1).strip().lower()].append(block.line)
    for label, lines in labels.items():
        if len(lines) >= 3:
            findings.append(Finding("warn", "шаблон", lines[0], f"{label}: ×{len(lines)}",
                                    "одна и та же метка в каждой карточке — текст читается как таблица"))
    starts: dict[tuple, list[int]] = defaultdict(list)
    for block in blocks:
        if block.kind == "paragraph":
            first = words(plain(block.text))[:2]
            if len(first) == 2:
                starts[tuple(first)].append(block.line)
    for start, lines in starts.items():
        if len(lines) >= 3:
            findings.append(Finding("warn", "шаблон", lines[0], f"«{' '.join(start)}…» ×{len(lines)}",
                                    "абзацы начинаются одинаково — начни по-разному"))


# Inflectional endings, longest first. A light stemmer is enough to see that
# «кирпичная» and «кирпич» or «можно» and «можно» are the same word.
ENDINGS = sorted(
    """
    иями ями ами ием иях ях ах ов ев ей ой ий ый ая яя ое ее ые ие ую юю ым им ом ем ых их
    ого его ому ему ыми ими ешь ишь ете ите ет ит ут ют ат ят ем им ла ло ли ть ти чь ся сь
    ия ья ие ье ию ью а я о е у ю ы и й ь
    """.split(),
    key=len,
    reverse=True,
)
# Words that repeat by nature. Modal and filler words («можно», «нужно», «очень»,
# «также») are deliberately not here: their repeats are the most visible ones.
FUNCTION_WORDS = set(
    """
    этот эта это эти этого этой этому этим этих этом тот та то те того той тому тем тех том
    такой такая такое такие таким таких такую так как если когда чтобы или либо чем что кто
    который которая которое которые которого которой которым которых котором которую
    свой своя своё свои своего своей своим своих свою его её их они она оно него нему ним ней
    нее неё нем нём вас вам ваш ваша ваше ваши вашего вашей вашим ваших нас нам наш наша наше
    наши нашего нашей нашим наших для при без через после перед между около над под про
    уже ещё тоже даже только лишь ли же бы есть быть был была было были будет будут может
    могут нет все всё весь вся всех всем всеми всего всей себя себе собой тоже там тут здесь
    где куда друг друга один одна одно одни одного одной раз два три года году лет более менее
    """.split()
)
# Modal and filler words stay countable even when they are frequent in the text.
ALWAYS_COUNT = {"можн", "нужн", "очен", "такж", "стоит", "сраз", "важн", "удобн", "прост"}


def stem(word: str) -> str:
    word = word.lower().replace("ё", "е")
    for ending in ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= 3:
            return word[: -len(ending)]
    return word


def same_root(a: str, b: str) -> bool:
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    if len(short) >= 4 and long_.startswith(short):
        return True
    common = 0
    for x, y in zip(a, b):
        if x != y:
            break
        common += 1
    return common >= 5


def content_stems(text: str) -> list[str]:
    return [stem(w) for w in words(text)
            if len(w) >= 4 and CYRILLIC_RE.match(w) and w.replace("ё", "е") not in FUNCTION_WORDS]


def shared_roots(first: list[str], second: list[str]) -> list[str]:
    found = []
    for a in first:
        if any(same_root(a, b) for b in second) and not any(same_root(a, f) for f in found):
            found.append(a)
    return found


def topic_stems(blocks) -> set[str]:
    """Topic words («бальзам» in an article about balms) repeat by design: they are
    reported only in a chain of three sentences in a row."""
    tokens = [s for b in blocks if b.kind not in ("table", "heading") for s in content_stems(plain(b.text))]
    freq = Counter(tokens)
    return {s for s, n in freq.items() if n >= max(5, len(tokens) // 150)} - ALWAYS_COUNT


def is_topic(st: str, topic: set[str]) -> bool:
    return any(same_root(st, t) for t in topic)


def check_repeats(blocks, findings):
    topic = topic_stems(blocks)

    for block, sentences in sentences_of(blocks):
        history: list[list[str]] = []
        for sentence in sentences:
            stems = content_stems(sentence)
            inside = []
            for i, a in enumerate(stems):
                if is_topic(a, topic):
                    continue
                if any(same_root(a, b) for b in stems[i + 1:]) and not any(same_root(a, f) for f in inside):
                    inside.append(a)
            reported = list(inside)
            if history:
                for root in shared_roots(stems, history[-1]):
                    if any(same_root(root, r) for r in reported):
                        continue
                    chain = len(history) >= 2 and any(same_root(root, b) for b in history[-2])
                    if not is_topic(root, topic) or chain:
                        reported.append(root)
            for root in reported:
                findings.append(Finding("warn", "повтор слова", block.line, short_quote(sentence),
                                        f"«{root}…» повторяется в этом или соседнем предложении — "
                                        "местоимение, опущение, другая конструкция; термин синонимом не заменяй"))
            history.append(stems)
    seen: dict[tuple, int] = {}
    reported_lines: set[tuple[int, int]] = set()
    for block in blocks:
        if block.kind in ("table", "heading"):
            continue
        ws = words(plain(block.text))
        for i in range(len(ws) - SHINGLE + 1):
            shingle = tuple(ws[i:i + SHINGLE])
            if sum(1 for w in shingle if CYRILLIC_RE.match(w)) < SHINGLE // 2 + 1:
                continue  # brand and product names repeat by design
            first = seen.setdefault(shingle, block.line)
            if first != block.line and (first, block.line) not in reported_lines:
                reported_lines.add((first, block.line))
                findings.append(Finding("warn", "повтор мысли", block.line, " ".join(shingle),
                                        f"та же формулировка уже была в строке {first}"))


QUOTED_RE = re.compile(r"«[^»]*»|\"[^\"]*\"")


def check_heading_echo(blocks, findings):
    topic = topic_stems(blocks)
    for prev, block in zip(blocks, blocks[1:]):
        if prev.kind != "heading" or block.kind not in ("paragraph", "item"):
            continue
        # Product and brand names in quotes or Latin script may open the card.
        heading = [s for s in content_stems(QUOTED_RE.sub(" ", plain(prev.text))) if not is_topic(s, topic)]
        sentences = split_sentences(plain(block.text))
        if not heading or not sentences:
            continue
        roots = shared_roots(content_stems(QUOTED_RE.sub(" ", sentences[0])), heading)
        if roots:
            findings.append(Finding("warn", "эхо заголовка", block.line, short_quote(sentences[0]),
                                    f"первая фраза повторяет корень заголовка («{'», «'.join(r + '…' for r in roots)}») — "
                                    "начни с ответа или новой информации"))


def check_actors(blocks, findings):
    for block, sentences in sentences_of(blocks):
        for sentence in sentences:
            for match in VAGUE_ACTOR_RE.finditer(sentence):
                findings.append(Finding("warn", "кто действует?", block.line, match.group(0),
                                        "размытый деятель без источника — кто именно и откуда это известно?"))
            for clause in re.split(r"[,;]", sentence):
                verb = IMPERSONAL_RE.search(clause)
                if not verb:
                    continue
                actor = ACTOR_RE.search(clause)
                if actor is None and not VAGUE_ACTOR_RE.search(clause):
                    findings.append(Finding("warn", "кто действует?", block.line, short_quote(sentence),
                                            f"«{verb.group(0)}» без деятеля — назови, кто и почему, переведи в "
                                            "свойство предмета или обратись к читателю"))
                elif actor is not None and not REASON_RE.search(sentence):
                    findings.append(Finding("warn", "кто действует?", block.line, short_quote(sentence),
                                            f"«{actor.group(0)} {verb.group(0)}» — а почему? назови причину"))


def lint(text: str) -> list[Finding]:
    blocks = parse_blocks(text)
    findings: list[Finding] = []
    check_patterns(blocks, findings)
    check_typography(blocks, findings)
    check_sentences(blocks, findings)
    check_attribution(blocks, findings)
    check_templates(blocks, findings)
    check_repeats(blocks, findings)
    check_heading_echo(blocks, findings)
    check_actors(blocks, findings)
    findings.sort(key=lambda f: (f.level != "error", f.line, f.category))
    return findings


def format_report(findings: list[Finding]) -> str:
    if not findings:
        return "Замечаний нет."
    errors = sum(f.level == "error" for f in findings)
    out = [f"Ошибок: {errors}, предупреждений: {len(findings) - errors}", ""]
    for f in findings:
        mark = "ОШИБКА" if f.level == "error" else "проверь"
        out.append(f"[{mark}] строка {f.line}, {f.category}: «{f.quote}» — {f.hint}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", help="Markdown file, or - for stdin")
    parser.add_argument("--json", action="store_true", help="print findings as JSON")
    args = parser.parse_args(argv)
    try:
        if args.path == "-":
            text = sys.stdin.buffer.read().decode("utf-8")
        else:
            text = Path(args.path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"cannot read {args.path}: {exc}", file=sys.stderr)
        return 2
    findings = lint(text)
    if args.json:
        print(json.dumps([asdict(f) for f in findings], ensure_ascii=False, indent=2))
    else:
        print(format_report(findings))
    return 1 if any(f.level == "error" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
