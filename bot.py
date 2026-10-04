import os
import json
import re
import random
import unicodedata
import logging
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

# =========================================================
# UTILIDADES
# =========================================================

def norm(s):
    s = unicodedata.normalize("NFD", s.upper())
    s = "".join(
        c for c in s
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^A-Z0-9 ]+", " ", s).strip()


def title_terms(title):
    return [
        norm(x)
        for x in re.split(r"[,;/]", title)
        if norm(x)
    ]


def chunks(text, limit=3000):
    text = (
        text.replace("¶", "")
        .replace("\r", "")
        .strip()
    )

    out = []

    while len(text) > limit:
        cut = text.rfind("\n\n", 0, limit)

        if cut < limit // 2:
            cut = text.rfind(". ", 0, limit)

        if cut < limit // 2:
            cut = text.rfind(" ", 0, limit)

        if cut < 1:
            cut = limit

        out.append(text[:cut].strip())
        text = text[cut:].strip()

    if text:
        out.append(text)

    return out


# =========================================================
# CARGAR DICCIONARIO
# =========================================================

INDEX = Path("vine_index.json")

if not INDEX.exists():
    raise SystemExit("Falta vine_index.json")

DATA = json.loads(
    INDEX.read_text(encoding="utf8")
)

KEYS = list(DATA)

TERM_MAP = {}

for key, entry in DATA.items():
    for term in title_terms(entry["title"]):
        TERM_MAP.setdefault(term, []).append(key)


# =========================================================
# ÍNDICE ALFABÉTICO
# =========================================================

# Ordenamos por el título visible del Vine.
ALPHABETICAL = sorted(
    KEYS,
    key=lambda k: norm(DATA[k]["title"])
)

LETTER_MAP = {}

for key in ALPHABETICAL:
    title = norm(DATA[key]["title"])

    if not title:
        continue

    letter = title[0]

    if letter.isalpha():
        LETTER_MAP.setdefault(letter, []).append(key)

LETTERS = sorted(LETTER_MAP)

INDEX_PER_PAGE = 12


def letters_keyboard():
    rows = []
    row = []

    for letter in LETTERS:
        row.append(
            InlineKeyboardButton(
                letter,
                callback_data=f"letter|{letter}|0"
            )
        )

        if len(row) == 5:
            rows.append(row)
            row = []

    if row:
        rows.append(row)

    rows.append([
        InlineKeyboardButton(
            "🎲 Entrada al azar",
            callback_data="random"
        )
    ])

    return InlineKeyboardMarkup(rows)


def letter_page(letter, page):
    entries = LETTER_MAP.get(letter, [])

    if not entries:
        return (
            "📚 No hay entradas con esa letra.",
            letters_keyboard()
        )

    total_pages = (
        len(entries) + INDEX_PER_PAGE - 1
    ) // INDEX_PER_PAGE

    page = max(0, min(page, total_pages - 1))

    start = page * INDEX_PER_PAGE
    end = start + INDEX_PER_PAGE

    visible = entries[start:end]

    rows = []

    for key in visible:
        rows.append([
            InlineKeyboardButton(
                DATA[key]["title"][:55],
                callback_data=f"v|{key}"
            )
        ])

    nav = []

    if page > 0:
        nav.append(
            InlineKeyboardButton(
                "◀️",
                callback_data=f"letter|{letter}|{page-1}"
            )
        )

    nav.append(
        InlineKeyboardButton(
            f"{page+1}/{total_pages}",
            callback_data="noop"
        )
    )

    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(
                "▶️",
                callback_data=f"letter|{letter}|{page+1}"
            )
        )

    rows.append(nav)

    rows.append([
        InlineKeyboardButton(
            "🔤 Todas las letras",
            callback_data="alphabet"
        ),
        InlineKeyboardButton(
            "🎲 Azar",
            callback_data="random"
        )
    ])

    text = (
        f"📚 ÍNDICE · {letter}\n\n"
        f"{len(entries)} entradas con esta letra."
    )

    return text, InlineKeyboardMarkup(rows)


# =========================================================
# MENÚ PRINCIPAL
# =========================================================

def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔤 Índice alfabético",
                callback_data="alphabet"
            )
        ],
        [
            InlineKeyboardButton(
                "🎲 Entrada al azar",
                callback_data="random"
            )
        ],
        [
            InlineKeyboardButton(
                "❓ Ayuda",
                callback_data="help"
            )
        ]
    ])


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "📖 Diccionario Bíblico Vine\n\n"
        "Escribe cualquier palabra para buscarla "
        "directamente en el diccionario.\n\n"
        "También puedes explorar el índice "
        "alfabético o descubrir una entrada al azar.",
        reply_markup=main_menu()
    )


async def ayuda(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "❓ AYUDA\n\n"
        "🔎 Escribe una palabra para buscarla.\n\n"
        "🔤 /indice — Explorar el diccionario "
        "por letra.\n\n"
        "🎲 /azar — Mostrar una entrada aleatoria.\n\n"
        "📖 /start — Abrir el menú principal."
    )


# =========================================================
# MOSTRAR ENTRADAS
# =========================================================

async def send_entry(message, key, random_button=False):
    entry = DATA[key]
    parts = chunks(entry["text"])

    for i, part in enumerate(parts, 1):

        head = f'📖 {entry["title"]}'

        if len(parts) > 1:
            head += f" — {i}/{len(parts)}"

        keyboard = None

        # El botón de otra entrada al azar solamente
        # aparece al final de una búsqueda aleatoria.
        if random_button and i == len(parts):
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🎲 Otra al azar",
                        callback_data="random"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔤 Índice alfabético",
                        callback_data="alphabet"
                    )
                ]
            ])

        await message.reply_text(
            head + "\n\n" + part,
            reply_markup=keyboard
        )


# =========================================================
# /INDICE
# =========================================================

async def indice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "📚 ÍNDICE ALFABÉTICO\n\n"
        "Selecciona una letra:",
        reply_markup=letters_keyboard()
    )


async def alphabet_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "📚 ÍNDICE ALFABÉTICO\n\n"
        "Selecciona una letra:",
        reply_markup=letters_keyboard()
    )


async def letter_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    try:
        _, letter, page = query.data.split("|")
        page = int(page)
    except Exception:
        return

    text, keyboard = letter_page(letter, page)

    await query.edit_message_text(
        text,
        reply_markup=keyboard
    )


# =========================================================
# /AZAR
# =========================================================

async def azar(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    key = random.choice(KEYS)

    await send_entry(
        update.message,
        key,
        random_button=True
    )


async def random_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer("🎲 Buscando...")

    key = random.choice(KEYS)

    # Quitamos los botones del mensaje anterior.
    try:
        await query.edit_message_reply_markup(
            reply_markup=None
        )
    except Exception:
        pass

    await send_entry(
        query.message,
        key,
        random_button=True
    )


# =========================================================
# BÚSQUEDA
# =========================================================

def candidates(q):

    if q in DATA:
        return [q]

    if q in TERM_MAP:
        return list(dict.fromkeys(TERM_MAP[q]))

    found = [
        k for k in KEYS
        if re.search(
            r"(^| )" + re.escape(q) + r"( |$)",
            k
        )
    ]

    return list(dict.fromkeys(found))


async def lookup(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    raw = (update.message.text or "").strip()
    q = norm(raw)

    if not q:
        return

    if len(q) > 60:
        await update.message.reply_text(
            "Envíame solamente la palabra "
            "o término que deseas buscar."
        )
        return

    found = candidates(q)

    if len(found) == 1:
        await send_entry(
            update.message,
            found[0]
        )
        return

    if len(found) > 1:
        keyboard = [
            [
                InlineKeyboardButton(
                    DATA[k]["title"][:55],
                    callback_data=f"v|{k}"
                )
            ]
            for k in found[:8]
        ]

        await update.message.reply_text(
            f"🔎 Encontré varias entradas "
            f"relacionadas con «{raw}».\n\n"
            "Elige una:",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            )
        )

        return

    choices = list(TERM_MAP)

    matches = process.extract(
        q,
        choices,
        scorer=fuzz.WRatio,
        limit=5,
        score_cutoff=65
    )

    if matches:
        keyboard = []
        seen = set()

        for term, _, _ in matches:
            for k in TERM_MAP[term]:

                if k not in seen:
                    seen.add(k)

                    keyboard.append([
                        InlineKeyboardButton(
                            DATA[k]["title"][:55],
                            callback_data=f"v|{k}"
                        )
                    ])

                    break

        await update.message.reply_text(
            f"🔎 No encontré una entrada exacta "
            f"para «{raw}».\n\n"
            "¿Quisiste decir?",
            reply_markup=InlineKeyboardMarkup(
                keyboard[:5]
            )
        )

    else:
        await update.message.reply_text(
            f"🔎 No encontré «{raw}» "
            "en el índice del diccionario."
        )


# =========================================================
# BOTONES DE ENTRADAS
# =========================================================

async def choose(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    key = query.data[2:]

    if key not in DATA:
        await query.edit_message_text(
            "Esa entrada ya no está disponible."
        )
        return

    # Si viene desde el índice, dejamos el índice disponible
    # y enviamos la definición debajo.
    await send_entry(
        query.message,
        key
    )


async def help_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "❓ AYUDA\n\n"
        "🔎 Escribe directamente una palabra.\n\n"
        "🔤 /indice — Índice alfabético.\n\n"
        "🎲 /azar — Entrada aleatoria.\n\n"
        "📖 /start — Menú principal.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔤 Índice",
                    callback_data="alphabet"
                ),
                InlineKeyboardButton(
                    "🎲 Azar",
                    callback_data="random"
                )
            ]
        ])
    )


async def noop(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.callback_query.answer()


async def error(update, context):
    logging.error(
        "Error del bot: %s",
        context.error
    )


# =========================================================
# INICIAR BOT
# =========================================================

def main():

    token = os.getenv("TELEGRAM_BOT_TOKEN")

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
        CommandHandler("ayuda", ayuda)
    )

    app.add_handler(
        CommandHandler("indice", indice)
    )

    app.add_handler(
        CommandHandler("azar", azar)
    )

    app.add_handler(
        CallbackQueryHandler(
            alphabet_callback,
            pattern=r"^alphabet$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            letter_callback,
            pattern=r"^letter\|"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            random_callback,
            pattern=r"^random$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            help_callback,
            pattern=r"^help$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            choose,
            pattern=r"^v\|"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            noop,
            pattern=r"^noop$"
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            lookup
        )
    )

    app.add_error_handler(error)

    print(
        f"Bot iniciado. "
        f"Entradas cargadas: {len(DATA)}"
    )

    print(
        f"Letras disponibles: "
        f"{', '.join(LETTERS)}"
    )

    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
