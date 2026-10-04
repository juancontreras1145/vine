import os
import json
import re
import unicodedata
import logging
import html
from pathlib import Path

from rapidfuzz import process, fuzz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)


# ============================================================
# TEXTO / BÚSQUEDA
# ============================================================

def norm(s):
    s = unicodedata.normalize("NFD", s.upper())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z0-9 ]+", " ", s).strip()


def title_terms(title):
    return [
        norm(x)
        for x in re.split(r"[,;/]", title)
        if norm(x)
    ]


def clean_text(text):
    # Símbolos residuales de la extracción del PDF.
    text = text.replace("¶", "")
    text = text.replace("\u00ad", "")
    text = text.replace("\r", "")

    # Espacios innecesarios.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# ============================================================
# SEPARACIÓN VISUAL DEL VINE
# ============================================================

ORDINALES = [
    "Primero",
    "Segundo",
    "Tercero",
    "Cuarto",
    "Quinto",
    "Sexto",
    "Séptimo",
    "Octavo",
    "Noveno",
    "Décimo",
]


def prepare_text(text):
    """
    Añade saltos visuales sin cambiar las palabras del diccionario.
    """
    text = clean_text(text)

    # A. Verbos / B. Nombres / etc.
    text = re.sub(
        r"(?<!\n)(?=\b[A-ZÁÉÍÓÚÑ]\.\s+"
        r"(?:Verbos?|Nombres?|Adjetivos?|Adverbios?|"
        r"Preposiciones?|Conjunciones?|Pronombres?|Participios?)\b)",
        "\n\n",
        text,
    )

    # Primero, Segundo, Tercero...
    ordinales = "|".join(ORDINALES)

    text = re.sub(
        rf"(?<!\n)(?=\b(?:{ordinales}),)",
        "\n\n",
        text,
        flags=re.IGNORECASE,
    )

    # Numeraciones 1. 2. 3. etc.
    # Evitamos en lo posible números pertenecientes a citas bíblicas.
    text = re.sub(
        r"(?<![\d\n])\s+(?=(?:[1-9]|1\d|20)\.\s+[A-Za-zÁÉÍÓÚÜÑáéíóúüñἀ-῾])",
        "\n\n",
        text,
    )

    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def format_html(text):
    """
    Convierte únicamente elementos estructurales en negrita.
    El contenido del Vine permanece intacto.
    """
    text = prepare_text(text)
    paragraphs = re.split(r"\n\s*\n", text)

    output = []

    for paragraph in paragraphs:
        p = paragraph.strip()

        if not p:
            continue

        safe = html.escape(p)

        # A. Verbos / B. Nombres...
        if re.match(
            r"^[A-ZÁÉÍÓÚÑ]\.\s+"
            r"(Verbos?|Nombres?|Adjetivos?|Adverbios?|"
            r"Preposiciones?|Conjunciones?|Pronombres?|Participios?)\b",
            p,
            re.I,
        ):
            first, *rest = p.split("\n", 1)

            if rest:
                output.append(
                    f"<b>{html.escape(first)}</b>\n"
                    f"{html.escape(rest[0])}"
                )
            else:
                output.append(f"<b>{html.escape(first)}</b>")

            continue

        # Primero, Segundo...
        matched = False

        for ordinal in ORDINALES:
            m = re.match(
                rf"^({ordinal})(,?)(.*)$",
                p,
                re.I | re.S,
            )

            if m:
                output.append(
                    f"<b>{html.escape(m.group(1))}</b>"
                    f"{html.escape(m.group(2))}"
                    f"{html.escape(m.group(3))}"
                )
                matched = True
                break

        if matched:
            continue

        # 1. término...
        m = re.match(r"^(\d+)\.\s*(.*)$", p, re.S)

        if m:
            output.append(
                f"<b>{m.group(1)}.</b> "
                f"{html.escape(m.group(2))}"
            )
            continue

        output.append(safe)

    return "\n\n".join(output).strip()


# ============================================================
# PAGINACIÓN
# ============================================================

PAGE_LIMIT = 1900


def pages(text, limit=PAGE_LIMIT):
    """
    Divide preferentemente por párrafos.
    Si un párrafo es demasiado largo, busca un punto.
    """
    text = prepare_text(text)

    paragraphs = [
        p.strip()
        for p in re.split(r"\n\s*\n", text)
        if p.strip()
    ]

    result = []
    current = ""

    for paragraph in paragraphs:

        candidate = (
            paragraph
            if not current
            else current + "\n\n" + paragraph
        )

        if len(candidate) <= limit:
            current = candidate
            continue

        if current:
            result.append(current)
            current = ""

        remaining = paragraph

        while len(remaining) > limit:

            cut = remaining.rfind(". ", 0, limit)

            if cut < int(limit * 0.55):
                cut = remaining.rfind("; ", 0, limit)

            if cut < int(limit * 0.55):
                cut = remaining.rfind(", ", 0, limit)

            if cut < int(limit * 0.55):
                cut = remaining.rfind(" ", 0, limit)

            if cut <= 0:
                cut = limit
            elif remaining[cut:cut + 2] == ". ":
                cut += 1

            result.append(remaining[:cut].strip())
            remaining = remaining[cut:].strip()

        current = remaining

    if current:
        result.append(current)

    return result or [""]


# ============================================================
# ÍNDICE
# ============================================================

INDEX = Path("vine_index.json")

if not INDEX.exists():
    raise SystemExit(
        "Falta vine_index.json."
    )

DATA = json.loads(
    INDEX.read_text(encoding="utf8")
)

KEYS = list(DATA)

TERM_MAP = {}

for key, entry in DATA.items():
    for term in title_terms(entry["title"]):
        TERM_MAP.setdefault(term, []).append(key)


# ============================================================
# MOSTRAR ENTRADA
# ============================================================

def navigation_keyboard(key, page, total):
    buttons = []

    if page > 0:
        buttons.append(
            InlineKeyboardButton(
                "◀️ Anterior",
                callback_data=f"p|{key}|{page-1}",
            )
        )

    buttons.append(
        InlineKeyboardButton(
            f"{page+1}/{total}",
            callback_data="noop",
        )
    )

    if page < total - 1:
        buttons.append(
            InlineKeyboardButton(
                "Siguiente ▶️",
                callback_data=f"p|{key}|{page+1}",
            )
        )

    return InlineKeyboardMarkup([buttons])


def entry_message(key, page):
    entry = DATA[key]

    title = entry["title"].strip()
    text = clean_text(entry["text"])

    # Evita repetir el título si ya viene al principio del texto.
    first_line = text.split("\n", 1)[0].strip()

    if norm(first_line) == norm(title):
        if "\n" in text:
            text = text.split("\n", 1)[1].strip()
        else:
            text = ""

    entry_pages = pages(text)

    page = max(0, min(page, len(entry_pages) - 1))

    body = format_html(entry_pages[page])

    header = (
        f"📖 <b>{html.escape(title)}</b>"
    )

    if len(entry_pages) > 1:
        header += (
            f"\n<i>Parte {page+1} de "
            f"{len(entry_pages)}</i>"
        )

    message = header

    if body:
        message += "\n\n" + body

    keyboard = None

    if len(entry_pages) > 1:
        keyboard = navigation_keyboard(
            key,
            page,
            len(entry_pages),
        )

    return message, keyboard


async def send_entry(message, key):
    text, keyboard = entry_message(key, 0)

    await message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


# ============================================================
# BÚSQUEDA
# ============================================================

def candidates(q):

    if q in DATA:
        return [q]

    if q in TERM_MAP:
        return list(
            dict.fromkeys(TERM_MAP[q])
        )

    found = [
        k
        for k in KEYS
        if re.search(
            r"(^| )" + re.escape(q) + r"( |$)",
            k,
        )
    ]

    return list(dict.fromkeys(found))


# ============================================================
# COMANDOS
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "📖 <b>Diccionario Bíblico Vine</b>\n\n"
        "Escribe una palabra para consultar "
        "el diccionario.\n\n"
        "Ejemplos:\n"
        "FE · GRACIA · BAUTISMO · "
        "CONTAMINAR · JUSTIFICACIÓN",
        parse_mode="HTML",
    )


async def lookup(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    raw = (update.message.text or "").strip()
    q = norm(raw)

    if not q:
        return

    if len(q) > 60:
        await update.message.reply_text(
            "Envíame solamente la palabra o "
            "término que deseas buscar."
        )
        return

    found = candidates(q)

    if len(found) == 1:
        await send_entry(
            update.message,
            found[0],
        )
        return

    if len(found) > 1:

        keyboard = [
            [
                InlineKeyboardButton(
                    DATA[k]["title"][:55],
                    callback_data=f"v|{k}",
                )
            ]
            for k in found[:8]
        ]

        await update.message.reply_text(
            f"🔎 Encontré varias entradas "
            f"relacionadas con «{raw}».\n\n"
            f"Elige una:",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
        )

        return

    # Por ahora mantenemos las sugerencias actuales.
    choices = list(TERM_MAP)

    matches = process.extract(
        q,
        choices,
        scorer=fuzz.WRatio,
        limit=5,
        score_cutoff=65,
    )

    if matches:

        keyboard = []
        seen = set()

        for term, _, _ in matches:

            for k in TERM_MAP[term]:

                if k not in seen:
                    seen.add(k)

                    keyboard.append(
                        [
                            InlineKeyboardButton(
                                DATA[k]["title"][:55],
                                callback_data=f"v|{k}",
                            )
                        ]
                    )

                    break

        await update.message.reply_text(
            f"🔎 No encontré una entrada exacta "
            f"para «{raw}».\n\n"
            f"¿Quisiste decir?",
            reply_markup=InlineKeyboardMarkup(
                keyboard[:5]
            ),
        )

    else:
        await update.message.reply_text(
            f"🔎 No encontré «{raw}» "
            f"en el índice del diccionario."
        )


# ============================================================
# BOTONES
# ============================================================

async def choose(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    key = query.data[2:]

    if key not in DATA:
        await query.edit_message_text(
            "Esa entrada ya no está disponible. "
            "Vuelve a escribir la palabra."
        )
        return

    await query.edit_message_reply_markup(
        reply_markup=None
    )

    await send_entry(
        query.message,
        key,
    )


async def change_page(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    try:
        _, key, page = query.data.split("|", 2)
        page = int(page)
    except Exception:
        return

    if key not in DATA:
        await query.edit_message_text(
            "Esta entrada ya no está disponible."
        )
        return

    text, keyboard = entry_message(
        key,
        page,
    )

    try:
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    except Exception as exc:
        # Telegram devuelve error si se pulsa dos veces
        # exactamente la misma página.
        if "Message is not modified" not in str(exc):
            raise


async def noop(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.callback_query.answer()


async def error(update, context):
    logging.error(
        "Error del bot",
        exc_info=context.error,
    )


# ============================================================
# INICIO
# ============================================================

def main():

    token = os.getenv(
        "TELEGRAM_BOT_TOKEN"
    )

    if not token:
        raise SystemExit(
            "Falta TELEGRAM_BOT_TOKEN. "
            "Ejecuta: set -a; source .env; set +a"
        )

    app = (
        Application.builder()
        .token(token)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("ayuda", start)
    )

    app.add_handler(
        CallbackQueryHandler(
            choose,
            pattern=r"^v\|",
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            change_page,
            pattern=r"^p\|",
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            noop,
            pattern=r"^noop$",
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            lookup,
        )
    )

    app.add_error_handler(error)

    print(
        f"Bot iniciado. "
        f"Entradas cargadas: {len(DATA)}"
    )

    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
