import json
import logging
import os
import random
import secrets
from datetime import datetime, timedelta

from dotenv import load_dotenv
from groq import Groq
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

from personality import (
    LENA_PERSONALITY,
    is_topic_forbidden,
    get_natural_deflection,
    get_sticker_for_response,
    is_bot_usage_attempt
)

# Загрузи переменные окружения
load_dotenv(dotenv_path='. env')

# Получи токены
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Резервные значения
if not TELEGRAM_BOT_TOKEN:
    TELEGRAM_BOT_TOKEN = "8146591194:AAG5fP-mOt_N0H8wuIIEwA5IvCJpFntVQyo"
if not GROQ_API_KEY:
    GROQ_API_KEY = "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"

CREATOR_ID = 1234567890

print(f"✅ Токен Telegram загружен: {TELEGRAM_BOT_TOKEN[: 20]}...")
print(f"✅ Groq API ключ загружен: {GROQ_API_KEY[:20]}...")

client = Groq(api_key=GROQ_API_KEY)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Папки
IMAGES_FOLDER = "images"
STICKERS_FOLDER = "stickers"
DIALOGS_FOLDER = "dialogs"

# Файлы данных
BLOCKED_USERS_FILE = "blocked_users. json"
ADMINS_FILE = "admins. json"
USER_LIMITS_FILE = "user_limits. json"
REFERRAL_FILE = "referral_data.json"
USER_STATS_FILE = "user_stats. json"

os.makedirs(DIALOGS_FOLDER, exist_ok=True)

# ===== КОНТЕНТ ЛЕНЫ (от друга) =====

WISDOM_TEXTS = [
    "Иногда важно не искать смысл.\nА просто позволить себе быть.\n*Лена тихо кивает.*",
    "Если тебе сейчас тяжело — это не делает тебя слабым.\nЭто значит, что ты долго держался.\n*Она смотрит с пониманием.*",
    "Не все ответы приходят сразу.\nИ это нормально.  Некоторые вещи нужно просто прожить.\n*Лена чуть пожимает плечами и улыбается.*",
    "Молчание иногда говорит больше, чем слова.\n*Она смотрит в глаза.*",
    "Ты не обязан быть сильным каждый день.\nИногда достаточно просто дышать.\n*Мягкая улыбка.*"
]

ABOUT_LENA = (
    "Меня зовут Лена.\n"
    "Я не люблю спешить и редко говорю громко.\n"
    "Иногда мне проще молчать, чем подбирать правильные слова.\n\n"
    "Я не обещаю, что станет легче сразу.\n"
    "Но если ты здесь — значит, ты уже не один.\n\n"
    "*Лена слегка улыбается.*"
)

THOUGHTS_TEXTS = [
    "Иногда я думаю, что самые тёплые моменты — это те, которые почти незаметны.\n*Мягкий стикер*",
    "Я не всегда знаю, как правильно.\nНо мне важно быть рядом, даже если молча.\n*Спокойный стикер*",
    "Тишина — это не пустота.\nИногда это просто место, где можно выдохнуть.\n*Нейтральный стикер*",
    "Каждый день ты становишься чуть сильнее.\nДаже если этого не видно.\n*Задумчивый взгляд.*",
    "Я верю в то, что ты справишься.\nПотому что ты уже столько пережил.\n*Тёплая улыбка.*"
]

GENTLE_TEXTS = {
    "🤍 Обнять": "*Лена обнимает тебя крепко*\nТы в безопасности.  Я здесь.",
    "🤍 Погладить": "*Лена нежно гладит тебя по голове*\nВсё будет хорошо.",
    "🤍 Просто быть рядом": "*Лена просто сидит рядом и молча поддерживает*\nТебе не нужно ничего говорить."
}

# Логика без повторов подряд
user_wisdom_index = {}
user_thoughts_index = {}
user_gentle_index = {}


def get_next_wisdom(user_id: int):
    if user_id not in user_wisdom_index:
        user_wisdom_index[user_id] = []

    used = user_wisdom_index[user_id]
    choices = [i for i in range(len(WISDOM_TEXTS)) if i not in used[-1:]]
    next_index = random.choice(choices)
    used.append(next_index)
    if len(used) > len(WISDOM_TEXTS):
        used.pop(0)
    user_wisdom_index[user_id] = used
    return WISDOM_TEXTS[next_index]


def get_next_thoughts(user_id: int):
    if user_id not in user_thoughts_index:
        user_thoughts_index[user_id] = []

    used = user_thoughts_index[user_id]
    choices = [i for i in range(len(THOUGHTS_TEXTS)) if i not in used[-1:]]
    next_index = random.choice(choices)
    used.append(next_index)
    if len(used) > len(THOUGHTS_TEXTS):
        used.pop(0)
    user_thoughts_index[user_id] = used
    return THOUGHTS_TEXTS[next_index]


# ===== МОДЕРАЦИЯ =====

def load_blocked_users() -> list:
    if os.path.exists(BLOCKED_USERS_FILE):
        try:
            with open(BLOCKED_USERS_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []


def save_blocked_users(blocked_list: list):
    try:
        with open(BLOCKED_USERS_FILE, 'w') as f:
            json.dump(blocked_list, f, indent=2)
    except Exception as e:
        logger.error(f"Ошибка при сохранении blocked_users. json: {e}")


def load_admins() -> list:
    if os.path.exists(ADMINS_FILE):
        try:
            with open(ADMINS_FILE, 'r') as f:
                admins = json.load(f)
                if CREATOR_ID not in admins:
                    admins.append(CREATOR_ID)
                    save_admins(admins)
                return admins
        except:
            return [CREATOR_ID]
    return [CREATOR_ID]


def save_admins(admin_list: list):
    try:
        with open(ADMINS_FILE, 'w') as f:
            json.dump(admin_list, f, indent=2)
    except Exception as e:
        logger.error(f"Ошибка при сохранении admins.json: {e}")


def is_user_blocked(user_id: int) -> bool:
    blocked = load_blocked_users()
    return user_id in blocked


def is_admin(user_id: int) -> bool:
    admins = load_admins()
    return user_id in admins


def block_user(user_id: int) -> bool:
    blocked = load_blocked_users()
    if user_id not in blocked:
        blocked.append(user_id)
        save_blocked_users(blocked)
        logger.info(f"🚫 Юзер {user_id} заблокирован")
        return True
    return False


def unblock_user(user_id: int) -> bool:
    blocked = load_blocked_users()
    if user_id in blocked:
        blocked.remove(user_id)
        save_blocked_users(blocked)
        logger.info(f"✅ Юзер {user_id} разблокирован")
        return True
    return False


def add_admin(user_id: int) -> bool:
    admins = load_admins()
    if user_id not in admins:
        admins.append(user_id)
        save_admins(admins)
        logger.info(f"👑 Юзер {user_id} стал админом")
        return True
    return False


def remove_admin(user_id: int) -> bool:
    if user_id == CREATOR_ID:
        return False
    admins = load_admins()
    if user_id in admins:
        admins.remove(user_id)
        save_admins(admins)
        logger.info(f"👑 Юзер {user_id} больше не админ")
        return True
    return False


# ===== ЛИМИТЫ =====

def load_user_limits() -> dict:
    if os.path.exists(USER_LIMITS_FILE):
        try:
            with open(USER_LIMITS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_user_limits(limits: dict):
    try:
        with open(USER_LIMITS_FILE, 'w', encoding='utf-8') as f:
            json.dump(limits, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка при сохранении user_limits.json: {e}")


def get_user_limit(user_id: int) -> dict:
    limits = load_user_limits()
    user_id_str = str(user_id)

    if user_id_str not in limits:
        limits[user_id_str] = {
            "user_id": user_id,
            "messages_today": 0,
            "daily_limit": 10,
            "last_reset": datetime.now().strftime("%Y-%m-%d"),
            "extra_messages": 0
        }
        save_user_limits(limits)

    return limits[user_id_str]


def reset_daily_limit(user_id: int):
    limits = load_user_limits()
    user_id_str = str(user_id)

    if user_id_str in limits:
        user_limit = limits[user_id_str]
        last_reset = datetime.strptime(user_limit["last_reset"], "%Y-%m-%d")
        today = datetime.now()

        if (today - last_reset).days >= 1:
            user_limit["messages_today"] = 0
            user_limit["last_reset"] = today.strftime("%Y-%m-%d")
            save_user_limits(limits)
            logger.info(f"♻️ Лимит сброшен для пользователя {user_id}")


def add_message(user_id: int) -> bool:
    reset_daily_limit(user_id)

    limits = load_user_limits()
    user_id_str = str(user_id)
    user_limit = get_user_limit(user_id)

    total_available = user_limit["daily_limit"] + user_limit["extra_messages"]

    if user_limit["messages_today"] < total_available:
        user_limit["messages_today"] += 1
        limits[user_id_str] = user_limit
        save_user_limits(limits)
        return True

    return False


def get_remaining_messages(user_id: int) -> int:
    reset_daily_limit(user_id)
    user_limit = get_user_limit(user_id)

    total_available = user_limit["daily_limit"] + user_limit["extra_messages"]
    remaining = total_available - user_limit["messages_today"]

    return max(0, remaining)


def add_bonus_messages(user_id: int, amount: int):
    limits = load_user_limits()
    user_id_str = str(user_id)
    user_limit = get_user_limit(user_id)

    user_limit["extra_messages"] += amount
    limits[user_id_str] = user_limit
    save_user_limits(limits)

    logger.info(f"🎁 Пользователю {user_id} добавлено {amount} бонусных сообщений")


def is_limit_exceeded(user_id: int) -> bool:
    reset_daily_limit(user_id)
    user_limit = get_user_limit(user_id)
    total_available = user_limit["daily_limit"] + user_limit["extra_messages"]

    return user_limit["messages_today"] >= total_available


def get_limit_info_text(user_id: int) -> str:
    reset_daily_limit(user_id)
    user_limit = get_user_limit(user_id)

    daily = user_limit["daily_limit"]
    extra = user_limit["extra_messages"]
    used = user_limit["messages_today"]
    total = daily + extra
    remaining = max(0, total - used)

    text = f"""
📊 **ТВА ЛИМИТ СООБЩЕНИЙ:**

💬 Использовано: {used}/{total}
📈 Осталось: {remaining}

📅 Базовый лимит: {daily}/день
🎁 Бонусные сообщения:  {extra}

⏰ Сброс лимита: завтра в 00:00
"""

    return text


# ===== РЕФЕРАЛЫ =====

def load_referral_data() -> dict:
    if os.path.exists(REFERRAL_FILE):
        try:
            with open(REFERRAL_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {"users": {}, "codes": {}}
    return {"users": {}, "codes": {}}


def save_referral_data(data: dict):
    try:
        with open(REFERRAL_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка при сохранении referral_data.json: {e}")


def generate_referral_code(user_id: int) -> str:
    data = load_referral_data()
    user_id_str = str(user_id)

    if user_id_str in data["users"]:
        return data["users"][user_id_str]["referral_code"]

    while True:
        code = secrets.token_urlsafe(6)[:6].lower()
        if code not in data["codes"]:
            break

    data["users"][user_id_str] = {
        "user_id": user_id,
        "referral_code": code,
        "referrals": [],
        "created_at": datetime.now().isoformat()
    }

    data["codes"][code] = user_id_str
    save_referral_data(data)

    logger.info(f"✅ Реферальный код создан для {user_id}:  {code}")
    return code


def add_referral(referral_code: str, new_user_id: int) -> bool:
    data = load_referral_data()

    if referral_code not in data["codes"]:
        return False

    referrer_id_str = data["codes"][referral_code]
    new_user_id_str = str(new_user_id)

    if new_user_id_str in data["users"]:
        return False

    referrer_data = data["users"][referrer_id_str]

    if new_user_id not in referrer_data["referrals"]:
        referrer_data["referrals"].append(new_user_id)
        save_referral_data(data)

        logger.info(f"🎁 Новый реферал {new_user_id} для {referrer_id_str}")
        return True

    return False


def get_referrer_id(referral_code: str) -> int:
    data = load_referral_data()

    if referral_code not in data["codes"]:
        return None

    referrer_id_str = data["codes"][referral_code]
    return int(referrer_id_str)


def get_referral_info(user_id: int) -> dict:
    data = load_referral_data()
    user_id_str = str(user_id)

    if user_id_str not in data["users"]:
        generate_referral_code(user_id)
        data = load_referral_data()

    user_data = data["users"][user_id_str]
    referral_count = len(user_data["referrals"])
    bonus_messages = referral_count * 3

    return {
        "referral_code": user_data["referral_code"],
        "referral_count": referral_count,
        "bonus_messages": bonus_messages,
        "referrals": user_data["referrals"]
    }


def get_referral_text(user_id: int, bot_username: str) -> str:
    info = get_referral_info(user_id)
    code = info["referral_code"]
    count = info["referral_count"]
    bonus = info["bonus_messages"]

    referral_link = f"https://t.me/{bot_username}?start=ref_{code}"

    text = f"""
🎁 **ТВОЯ РЕФЕРАЛЬНАЯ ПРОГРАММА:**

📌 Твой код: `{code}`
🔗 Твоя ссылка: 
[Пригласить друга]({referral_link})

👥 Приглашено друзей:  {count}
🎉 Бонусных сообщений: +{bonus}

💡 За каждого приглашённого друга ты получаешь: 
📈 +3 сообщений к твоему лимиту!   
"""

    return text


# ===== АНАЛИТИКА =====

def load_user_stats() -> dict:
    if os.path.exists(USER_STATS_FILE):
        try:
            with open(USER_STATS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_user_stats(stats: dict):
    try:
        with open(USER_STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка при сохранении user_stats. json: {e}")


def update_user_stats(user_id: int, username: str):
    stats = load_user_stats()
    user_id_str = str(user_id)

    if user_id_str not in stats:
        stats[user_id_str] = {
            "user_id": user_id,
            "username": username,
            "messages_count": 0,
            "first_message": datetime.now().isoformat(),
            "last_message": datetime.now().isoformat(),
            "is_blocked": False
        }

    stats[user_id_str]["messages_count"] += 1
    stats[user_id_str]["last_message"] = datetime.now().isoformat()
    stats[user_id_str]["username"] = username

    save_user_stats(stats)


def get_total_users() -> int:
    stats = load_user_stats()
    return len(stats)


def get_active_users() -> int:
    from datetime import timedelta
    stats = load_user_stats()
    active = 0

    for user_data in stats.values():
        try:
            last_msg = datetime.fromisoformat(user_data.get("last_message", ""))
            if datetime.now() - last_msg < timedelta(days=7):
                active += 1
        except:
            pass

    return active


def get_top_users(limit: int = 10) -> list:
    stats = load_user_stats()

    sorted_users = sorted(
        stats.values(),
        key=lambda x: x.get("messages_count", 0),
        reverse=True
    )

    return sorted_users[:limit]


def get_total_messages() -> int:
    stats = load_user_stats()
    total = 0

    for user_data in stats.values():
        total += user_data.get("messages_count", 0)

    return total


def get_all_users() -> list:
    stats = load_user_stats()
    return list(stats.values())


def get_statistics_text() -> str:
    total_users = get_total_users()
    active_users = get_active_users()
    total_messages = get_total_messages()

    avg_messages = round(total_messages / total_users, 2) if total_users > 0 else 0

    text = f"""
📊 **СТАТИСТИКА БОТА ЛЕНЫ:**

👥 Всего пользователей: {total_users}
🟢 Активных (7 дней): {active_users}
💬 Всего сообщений: {total_messages}
📈 Среднее сообщений/юзер: {avg_messages}
"""

    return text


def get_top_users_text(limit: int = 10) -> str:
    top_users = get_top_users(limit)

    if not top_users:
        return "Нет данных о пользователях"

    text = f"🏆 **ТОП {limit} АКТИВНЫХ ПОЛЬЗОВАТЕЛЕЙ:**\n\n"

    for i, user in enumerate(top_users, 1):
        username = user.get("username", "Unknown")
        messages = user.get("messages_count", 0)
        user_id = user.get("user_id", "Unknown")

        text += f"{i}. @{username} (ID: {user_id}) - {messages} 💬\n"

    return text


def get_users_list_text() -> str:
    all_users = get_all_users()

    if not all_users:
        return "Нет данных о пользователях"

    text = f"📋 **СПИСОК ВСЕХ ПОЛЬЗОВАТЕЛЕЙ ({len(all_users)}):**\n\n"

    for i, user in enumerate(all_users, 1):
        username = user.get("username", "Unknown")
        messages = user.get("messages_count", 0)
        user_id = user.get("user_id", "Unknown")

        text += f"{i}.  @{username} (ID: {user_id}) - {messages} сообщений\n"

    return text


# ===== РАБОТА С ДИАЛОГАМИ =====

def get_dialog_file(user_id: int) -> str:
    return os.path.join(DIALOGS_FOLDER, f"user_{user_id}_dialogs.json")


def load_dialog_history(user_id: int) -> list:
    dialog_file = get_dialog_file(user_id)

    if os.path.exists(dialog_file):
        try:
            with open(dialog_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка при загрузке диалога: {e}")
            return []

    return []


def save_dialog_history(user_id: int, dialog_history: list):
    dialog_file = get_dialog_file(user_id)

    try:
        with open(dialog_file, 'w', encoding='utf-8') as f:
            json.dump(dialog_history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка при сохранении диалога: {e}")


def add_to_history(user_id: int, role: str, message: str):
    history = load_dialog_history(user_id)

    history.append({
        "role": role,
        "content": message,
        "timestamp": datetime.now().isoformat()
    })

    if len(history) > 20:
        history = history[-20:]

    save_dialog_history(user_id, history)
    return history


def get_history_for_prompt(user_id: int) -> list:
    history = load_dialog_history(user_id)

    messages = []
    for msg in history:
        messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })

    return messages


# ===== ПОЛУЧИТЬ СЛУЧАЙНОЕ ФОТО =====

def get_random_image() -> str:
    if not os.path.exists(IMAGES_FOLDER):
        return None

    images = [f for f in os.listdir(IMAGES_FOLDER) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]

    if not images:
        return None

    return os.path.join(IMAGES_FOLDER, random.choice(images))


# ===== ПОЛУЧИТЬ СТИКЕР В ТЕМУ =====

def get_sticker_file(sticker_name: str) -> str:
    if not sticker_name:
        return None

    if not os.path.exists(STICKERS_FOLDER):
        logger.warning(f"❌ Папка {STICKERS_FOLDER} не существует!")
        return None

    sticker_path = os.path.join(STICKERS_FOLDER, sticker_name)

    if os.path.exists(sticker_path):
        logger.info(f"✅ Найден стикер: {sticker_path}")
        return sticker_path
    else:
        logger.warning(f"❌ Стикер не найден: {sticker_path}")
        return None


# ===== МЕНЮ ЛЕНЫ (от друга) =====

def main_menu():
    """Главное меню с кнопками контента от друга"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🌸 О Лене")],
            [KeyboardButton(text="💜 Мудрые слова")],
            [KeyboardButton(text="🎐 Мысли Лены")],
            [KeyboardButton(text="🤍 Тепло")],
            [KeyboardButton(text="💬 Общаться")]
        ],
        resize_keyboard=True
    )


def gentle_menu():
    """Подменю Тепла"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🤍 Обнять")],
            [KeyboardButton(text="🤍 Погладить")],
            [KeyboardButton(text="🤍 Просто быть рядом")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )


# ===== ГЛАВНОЕ МЕНЮ (старое, для совместимости) =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start — показ главного меню"""
    user_id = update.effective_user.id
    username = update.effective_user.first_name or "Друг"

    # Проверяем, есть ли реферальный код
    if context.args:
        ref_code = context.args[0]

        if ref_code.startswith("ref_"):
            ref_code = ref_code[4:]

            referrer_id = get_referrer_id(ref_code)

            if referrer_id and add_referral(ref_code, user_id):
                add_bonus_messages(referrer_id, 3)

                logger.info(f"✅ Реферал добавлен: {user_id} -> {referrer_id}")

                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=f"🎉 Твой друг присоединился по твоей ссылке!\n\n🎁 Ты получил +3 сообщения к лимиту!"
                    )
                except:
                    pass

    # Новое меню от друга
    keyboard = main_menu()
    text = "🌸 Привет!  Я Лена!\n\nЧто ты хочешь узнать?"

    if update.message:
        await update.message.reply_text(text, reply_markup=keyboard)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)


# ===== ОБРАБОТЧИК ТЕКСТОВЫХ КНОПОК (от друга) =====

async def handle_text_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых кнопок меню"""
    user_id = update.effective_user.id
    text = update.message.text

    if text == "🌸 О Лене":
        await update.message.reply_text(ABOUT_LENA)
        return

    elif text == "💜 Мудрые слова":
        wisdom = get_next_wisdom(user_id)
        await update.message.reply_text(wisdom)
        return

    elif text == "🎐 Мысли Лены":
        thoughts = get_next_thoughts(user_id)
        await update.message.reply_text(thoughts)
        return

    elif text == "🤍 Тепло":
        keyboard = gentle_menu()
        await update.message.reply_text("Выбери что-то из предложенного 💜", reply_markup=keyboard)
        return

    elif text in GENTLE_TEXTS:
        response = GENTLE_TEXTS[text]
        await update.message.reply_text(response)
        keyboard = gentle_menu()
        await update.message.reply_text("Ещё раз? ", reply_markup=keyboard)
        return

    elif text == "⬅️ Назад":
        keyboard = main_menu()
        await update.message.reply_text("Что дальше?", reply_markup=keyboard)
        return

    elif text == "💬 Общаться":
        # Переходим в режим общения с ИИ
        context.user_data['mode'] = 'ai_lena'
        await update.message.reply_text(
            "✨ Теперь ты общаешься с Леной!\n\n"
            "Напиши сообщение, и Лена ответит!\n\n"
            "Команда /menu для возврата в главное меню."
        )
        return


# ===== КОМАНДЫ АДМИНИСТРАЦИИ =====

async def block_user_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text("❌ Только администраторы!")
        return

    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Используй:  /block <user_id>")
        return

    if block_user(target_id):
        await update.message.reply_text(f"✅ Пользователь {target_id} заблокирован!")
    else:
        await update.message.reply_text(f"⚠️ Пользователь уже заблокирован!")


async def unblock_user_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text("❌ Только администраторы!")
        return

    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Используй: /unblock <user_id>")
        return

    if unblock_user(target_id):
        await update.message.reply_text(f"✅ Пользователь разблокирован!")
    else:
        await update.message.reply_text(f"⚠️ Не в списке заблокированных!")


async def add_admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != CREATOR_ID:
        await update.message.reply_text("❌ Только создатель!")
        return

    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Используй: /addadmin <user_id>")
        return

    if add_admin(target_id):
        await update.message.reply_text(f"✅ Пользователь теперь админ!")
    else:
        await update.message.reply_text(f"⚠️ Уже админ!")


async def remove_admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != CREATOR_ID:
        await update.message.reply_text("❌ Только создатель!")
        return

    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Используй: /removeadmin <user_id>")
        return

    if remove_admin(target_id):
        await update.message.reply_text(f"✅ Больше не админ!")
    else:
        await update.message.reply_text(f"⚠️ Создатель!")


# ===== КОМАНДЫ АНАЛИТИКИ =====

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text("❌ Только администраторы!")
        return

    stats_text = get_statistics_text()
    await update.message.reply_text(stats_text, parse_mode="Markdown")


async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text("❌ Только администраторы!")
        return

    top_text = get_top_users_text(10)
    await update.message.reply_text(top_text, parse_mode="Markdown")


async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text("❌ Только администраторы!")
        return

    users_text = get_users_list_text()

    if len(users_text) > 4096:
        parts = [users_text[i:i + 4096] for i in range(0, len(users_text), 4096)]
        for part in parts:
            await update.message.reply_text(part, parse_mode="Markdown")
    else:
        await update.message.reply_text(users_text, parse_mode="Markdown")


async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != CREATOR_ID:
        await update.message.reply_text("❌ Только создатель!")
        return

    if not context.args:
        await update.message.reply_text("❌ Используй: /broadcast <сообщение>")
        return

    broadcast_message = ' '.join(context.args)

    await update.message.reply_text(f"📢 Рассылка: {broadcast_message}\n⏳ Отправляю...")

    all_users = get_all_users()
    sent_count = 0
    failed_count = 0

    for user_data in all_users:
        target_user_id = user_data.get("user_id")

        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"📢 **РАССЫЛКА:**\n\n{broadcast_message}",
                parse_mode="Markdown"
            )
            sent_count += 1
        except Exception as e:
            failed_count += 1

    report = f"✅ **РАССЫЛКА ЗАВЕРШЕНА! **\n- Отправлено: {sent_count}\n- Ошибок: {failed_count}"
    await update.message.reply_text(report, parse_mode="Markdown")


# ===== КОМАНДЫ ЛИМИТОВ И РЕФЕРАЛОВ =====

async def limit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    limit_text = get_limit_info_text(user_id)
    await update.message.reply_text(limit_text, parse_mode="Markdown")


async def ref_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    bot_info = await context.bot.get_me()
    bot_username = bot_info.username

    ref_text = get_referral_text(user_id, bot_username)
    await update.message.reply_text(ref_text, parse_mode="Markdown")


# ===== ОБРАБОТКА СООБЩЕНИЙ (ОБЩЕНИЕ С ИИ) =====

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений для общения с ИИ"""

    if context.user_data.get('mode') != 'ai_lena':
        return

    user_message = update.message.text
    user_id = update.effective_user.id
    username = update.effective_user.first_name or "Друг"

    # ОБНОВЛЯЕМ СТАТИСТИКУ
    update_user_stats(user_id, username)

    # ПРОВЕРКА БЛОКИРОВКИ
    if is_user_blocked(user_id):
        await update.message.reply_text(
            "😔 Увы, но вы заблокированы в боте.\n\n"
            "Для разбана:  @TrueUkraineHuman666"
        )
        return

    # ПРОВЕРКА ЛИМИТА
    if is_limit_exceeded(user_id):
        await update.message.reply_text(
            f"⏰ Лимит исчерпан на сегодня!\n\n"
            f"💡 Используй /ref чтобы пригласить друзей!\n\n"
            f"⏳ Обновится завтра в 00:00"
        )
        return

    # Добавляем сообщение в счётчик
    add_message(user_id)

    # Проверка на ChatGPT абуз
    if is_bot_usage_attempt(user_message):
        await update.message.reply_text(
            "Хм, я не помощник и не ИИ 😄\n"
            "Я просто твоя подруга Лена!\n\n"
            "Давай поговорим о чём-то личном?"
        )
        return

    # Проверка на запрещённые темы
    if is_topic_forbidden(user_message):
        await update.message.reply_text(get_natural_deflection())
        return

    # Показ "печатает..."
    await update.message.chat.send_action("typing")

    try:
        # Добавляем сообщение в историю
        add_to_history(user_id, "user", user_message)

        # Загружаем историю
        history_messages = get_history_for_prompt(user_id)

        # Готовим для Groq
        messages_for_groq = [
            {
                "role": "system",
                "content": LENA_PERSONALITY + f"\n\nИмя пользователя: {username}"
            }
        ]

        messages_for_groq.extend(history_messages)

        # Запрос к Groq
        chat_completion = client.chat.completions.create(
            messages=messages_for_groq,
            model="llama-3.3-70b-versatile",
            max_tokens=300,
            temperature=0.9
        )

        lena_response = chat_completion.choices[0].message.content.strip()

        # Добавляем в историю
        add_to_history(user_id, "assistant", lena_response)

        logger.info(f"📝 Ответ Лены: {lena_response}")

        # ПРОВЕРЯЕМ СТИКЕР
        sticker_name = get_sticker_for_response(lena_response, user_id)

        if sticker_name:
            sticker_path = get_sticker_file(sticker_name)

            if sticker_path:
                try:
                    with open(sticker_path, 'rb') as sticker:
                        await update.message.reply_sticker(sticker=sticker)
                except Exception as e:
                    logger.error(f"❌ Ошибка стикера: {e}")

        # Отправляем ответ
        await update.message.reply_text(lena_response)

        # Показываем оставшиеся сообщения
        remaining = get_remaining_messages(user_id)
        if remaining <= 3:
            await update.message.reply_text(
                f"⚠️ Осталось {remaining} сообщений!\n\n"
                f"Используй /ref чтобы пригласить друзей!"
            )

    except Exception as e:
        logger.error(f"❌ Error:  {e}")
        await update.message.reply_text("Что-то пошло не так...  😔")


# ===== КОМАНДА /menu =====

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['mode'] = None
    keyboard = main_menu()
    await update.message.reply_text("Что дальше?", reply_markup=keyboard)


# ===== КОМАНДА /clear =====

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    dialog_file = get_dialog_file(user_id)

    if os.path.exists(dialog_file):
        os.remove(dialog_file)
        await update.message.reply_text("✅ История очищена!")
    else:
        await update.message.reply_text("Истории нет")


# ===== ГЛАВНАЯ ФУНКЦИЯ =====

def main():
    """Запуск бота"""
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("clear", clear_history))

    # КОМАНДЫ АДМИНИСТРАЦИИ
    app.add_handler(CommandHandler("block", block_user_cmd))
    app.add_handler(CommandHandler("unblock", unblock_user_cmd))
    app.add_handler(CommandHandler("addadmin", add_admin_cmd))
    app.add_handler(CommandHandler("removeadmin", remove_admin_cmd))

    # КОМАНДЫ АНАЛИТИКИ
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("top", top_cmd))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))

    # КОМАНДЫ ЛИМИТОВ И РЕФЕРАЛОВ
    app.add_handler(CommandHandler("limit", limit_cmd))
    app.add_handler(CommandHandler("ref", ref_cmd))

    # ОБРАБОТЧИК ТЕКСТОВЫХ КНОПОК (от друга) - ДО остальных
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_buttons))

    # Обработчик сообщений для ИИ (если не обработалось как кнопка)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 БОТ ЛЕНЫ ЗАПУЩЕН!")
    print("Нажми CTRL+C для остановки...")

    app.run_polling()


if __name__ == "__main__":
    main()