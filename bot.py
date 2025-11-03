import os
import json
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from difflib import get_close_matches

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Optional: OpenAI for AI answers / translation
try:
    import openai
except Exception:
    openai = None

load_dotenv()
TELEGRAM_TOKEN = os.getenv("8283050861:AAEOwq2JG4ZIU-GGCz4TVE5s-vQ_zsd5tKI")
OPENAI_API_KEY = os.getenv("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")
STICKER_ID = os.getenv("STICKER_ID")  # optional

if OPENAI_API_KEY and openai:
    openai.api_key = OPENAI_API_KEY

# --- Simple persistent store for user language preferences ---
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
USERS_FILE = DATA_DIR / "users.json"

def load_users():
    if USERS_FILE.exists():
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    return {}

def save_users(d):
    USERS_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

users = load_users()

# --- FAQ: use the Russian text you provided ---
FAQ_RU = {
    "1": {
        "q": "Кто имеет право голосовать вне помещения для голосования?",
        "a": "В случае, когда отдельные избиратели по состоянию здоровья, по причине ухода за больным членом семьи, а также находящиеся в отдаленных и труднодоступных районах, где не образованы избирательные участки, не могут прибыть для голосования, участковая избирательная комиссия по их письменной просьбе, должна организовать голосование в месте пребывания этих избирателей."
    },
    "2": {
        "q": "Как можно подать заявление на голосование вне помещения?",
        "a": "Написать заявление об организации голосования в месте пребывания избирателя в участковую избирательную комиссию (УИК)."
    },
    "3": {
        "q": "В какие сроки можно подать заявление?",
        "a": "Заявление может быть подано со дня представления избирателям списков избирателей избирательными комиссиями для ознакомления не позднее двенадцати часов местного времени в день голосования."
    },
    "4": {
        "q": "Нужны ли документы или справки для подтверждения причины?",
        "a": "✔️ Нет. Основание считается достоверным, если избиратель сообщил его сам."
    },
    "5": {
        "q": "Какие документы должен предъявить избиратель при голосовании на дому?",
        "a": "При голосовании вне помещения для голосования бюллетень (бюллетени) выдается избирателям по предъявлении документа, удостоверяющего личность избирателя, на основании заявления о голосовании вне помещения для голосования, о чем они расписываются в заявлении."
    },
    "6": {
        "q": "Кто приходит к избирателю?",
        "a": "При организации голосования вне помещения для голосования переносную урну сопровождают два члена избирательной комиссии. При выезде членов избирательной комиссии для организации голосования вне помещения для голосования их вправе сопровождать наблюдатели либо доверенные лица."
    },
    "7": {
        "q": "До какого времени можно подать заявление для голосования вне помещения?",
        "a": "Не позднее 12 часов местного времени, в день голосования."
    },
    "8": {
        "q": "Можно ли отказаться от голосования, если уже подал заявку?",
        "a": "✔️ Да, нужно уведомить участковую комиссию заранее."
    },
    "9": {
        "q": "Засчитываются ли голоса, поданные на дому?",
        "a": "✔️ Да, бюллетени опускаются в переносную урну и учитываются наравне с другими."
    },
    "10": {
        "q": "Кто контролирует законность голосования вне помещения?",
        "a": "✔️ Наблюдатели, доверенные лица кандидатов, представители СМИ."
    }
}

# We'll store FAQ_KZ either prefilled or generated at runtime (via OpenAI)
FAQ_KZ = {}  # will be filled automatically if openai available, else empty

# --- Utility: try to auto-translate RU -> KZ via OpenAI (optional) ---
async def generate_kz_faq_if_needed():
    if not OPENAI_API_KEY or not openai:
        return
    global FAQ_KZ
    if FAQ_KZ:
        return  # already have
    # Build prompt to translate pairs reliably
    pairs = []
    for k, v in FAQ_RU.items():
        pairs.append({"q": v["q"], "a": v["a"]})
    prompt = (
        "Переведи на казахский язык следующие вопросы и ответы для FAQ. "
        "Верни JSON-объект где ключи такие же (\"1\",\"2\"...) а значения имеют поля 'q' и 'a'.\n\n"
        f"{json.dumps(pairs, ensure_ascii=False, indent=2)}\n\n"
        "Точная и формальная казахская юридическая формулировка желательна."
    )
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",  # поменяйте на доступную модель
            messages=[{"role":"user","content":prompt}],
            max_tokens=1500,
            temperature=0.0,
        )
        text = resp.choices[0].message.content
        # ожидание: JSON; попытаемся распарсить
        parsed = json.loads(text)
        # преобразуем в FAQ_KZ в том же формате
        for i, entry in enumerate(parsed, start=1):
            # Если модель выдала список
            pass
    except Exception:
        # на случай ошибки — попытка упростить: делать по одному вызову на пункт
        FAQ_KZ = {}
        for k, v in FAQ_RU.items():
            try:
                prompt = f"Переведи на казахский: Вопрос: {v['q']}\nОтвет: {v['a']}\nДай в компактном виде только перевод вопроса и перевода ответа."
                resp = openai.ChatCompletion.create(
                    model="gpt-4o-mini",
                    messages=[{"role":"user","content":prompt}],
                    max_tokens=400,
                    temperature=0.0,
                )
                text = resp.choices[0].message.content.strip().split("\n")
                q_kz = text[0].strip()
                a_kz = " ".join(text[1:]).strip()
                FAQ_KZ[k] = {"q": q_kz, "a": a_kz}
            except Exception:
                FAQ_KZ[k] = {"q": v["q"], "a": v["a"]}  # fallback to RU
    # if parsing not done above, try to merge
    if not FAQ_KZ:
        try:
            # sometimes model returns a dict with numeric keys
            parsed_json = json.loads(text)
            for idx, entry in enumerate(parsed_json, start=1):
                key = str(idx)
                if isinstance(entry, dict) and "q" in entry and "a" in entry:
                    FAQ_KZ[key] = {"q": entry["q"], "a": entry["a"]}
        except Exception:
            # final fallback: leave empty
            FAQ_KZ = {}

# --- Helpers for language ---
def get_user_lang(user_id: str):
    return users.get(str(user_id), {}).get("lang", "ru")

def set_user_lang(user_id: str, lang: str):
    users.setdefault(str(user_id), {})["lang"] = lang
    save_users(users)

# --- Matching user question to FAQ (fuzzy) ---
def find_faq_answer(text: str, lang: str, cutoff=0.6):
    pool = {}
    if lang == "ru":
        for k,v in FAQ_RU.items():
            pool[v["q"]] = v["a"]
    else:
        for k,v in FAQ_KZ.items():
            pool[v["q"]] = v["a"]
    # if pool empty (no translations), fallback to Russian
    if not pool:
        for k,v in FAQ_RU.items():
            pool[v["q"]] = v["a"]
    keys = list(pool.keys())
    matches = get_close_matches(text, keys, n=1, cutoff=cutoff)
    if matches:
        return pool[matches[0]]
    return None

# --- OpenAI answer (fallback) ---
async def ask_openai(question: str, lang: str):
    if not OPENAI_API_KEY or not openai:
        return None
    # Prepare system prompt to answer courteously, concisely, with emojis and in language requested
    lang_name = "Russian" if lang == "ru" else "Kazakh"
    system = (
        f"You are an assistant answering about voting procedures. "
        f"Answer in {lang_name}. Keep answer concise (3-6 sentences), include relevant emoji "
        f"where appropriate and be friendly. If question relates to home voting, prefer to mention "
        f"that official rules may vary and encourage contacting the local precinct."
    )
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role":"system","content":system},
                {"role":"user","content":question},
            ],
            max_tokens=400,
            temperature=0.0,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return None

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    # default language ru
    set_user_lang(uid, "ru")
    # sticker if provided
    if STICKER_ID:
        try:
            await context.bot.send_sticker(chat_id=uid, sticker=STICKER_ID)
        except Exception:
            pass
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Русский 🇷🇺", callback_data="lang_ru"),
                                InlineKeyboardButton("Қазақша 🇰🇿", callback_data="lang_kz")]])
    text = "👋 Вас приветствует бот «Выборы Караменды»!\n\nЗадайте любой вопрос по голосованию — бот ответит на русском или казахском. Используйте эмоции и стикеры для оформления."
    # Russian start text provided by you
    await context.bot.send_message(chat_id=uid, text=text, reply_markup=kb)

async def lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id
    if data == "lang_ru":
        set_user_lang(uid, "ru")
        await query.edit_message_text("Язык установлен: Русский 🇷🇺\nЗадайте вопрос или напишите номер из FAQ (1–10).")
    else:
        set_user_lang(uid, "kz")
        await query.edit_message_text("Тіл орнатылды: Қазақша 🇰🇿\nСұрақ қойыңыз немесе FAQ-тан 1–10 нөмірін теріңіз.")
        # ensure translations exist (async)
        if OPENAI_API_KEY:
            asyncio.create_task(generate_kz_faq_if_needed())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = get_user_lang(uid)
    if lang == "ru":
        await update.message.reply_text("Напишите вопрос или номер пункта FAQ (1–10). Чтобы сменить язык — /start.")
    else:
        await update.message.reply_text("Сұрақ қойыңыз немесе FAQ-тан 1–10 нөмірін теріңіз. Тілді ауыстыру үшін /start.")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = (update.message.text or "").strip()
    lang = get_user_lang(uid)
    # if user sent number 1-10 -> return exact answer
    if text.isdigit() and text in FAQ_RU:
        key = text
        if lang == "ru":
            a = FAQ_RU[key]["a"]
        else:
            a = FAQ_KZ.get(key, {}).get("a") or FAQ_RU[key]["a"]
        # decorate with emoji
        await update.message.reply_text(f"✅ {a}")
        return

    # try to match to FAQ with fuzzy
    ans = find_faq_answer(text, lang)
    if ans:
        # decorate
        await update.message.reply_text(f"💡 {ans}")
        return

    # fallback: ask OpenAI (if available)
    ai_ans = await ask_openai(text, lang)
    if ai_ans:
        # small formatting: add sticker-like emoji prefix
        await update.message.reply_text(f"🤖 {ai_ans}")
        return

    # final fallback: reply in selected language with generic message
    if lang == "ru":
        await update.message.reply_text("Извините, не смог найти ответ. Можете задать вопрос иначе или написать номер пункта FAQ (1–10).")
    else:
        await update.message.reply_text("Кешіріңіз, жауап тауып бермеді. Сұрағыңызды басқа сөзбен қойыңыз немесе FAQ-тан 1–10 нөмірін теріңіз.")

# --- Main runner ---
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(lang_callback, pattern=r"^lang_"))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
