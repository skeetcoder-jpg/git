import json
import os
import logging

logger = logging.getLogger(__name__)

BLOCKED_USERS_FILE = "blocked_users.json"
ADMINS_FILE = "admins. json"

# ID создателя (твой ID)
CREATOR_ID = 8409895106  # ЗАМЕНИ НА СВОЙ ID!


def load_blocked_users() -> list:
    """Загружает список заблокированных юзеров"""
    if os.path.exists(BLOCKED_USERS_FILE):
        try:
            with open(BLOCKED_USERS_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []


def save_blocked_users(blocked_list: list):
    """Сохраняет список заблокированных юзеров"""
    try:
        with open(BLOCKED_USERS_FILE, 'w') as f:
            json.dump(blocked_list, f, indent=2)
    except Exception as e:
        logger.error(f"Ошибка при сохранении blocked_users. json:  {e}")


def load_admins() -> list:
    """Загружает список админов"""
    if os.path.exists(ADMINS_FILE):
        try:
            with open(ADMINS_FILE, 'r') as f:
                admins = json.load(f)
                # Добавляем создателя (он всегда админ)
                if CREATOR_ID not in admins:
                    admins.append(CREATOR_ID)
                    save_admins(admins)
                return admins
        except:
            return [CREATOR_ID]
    return [CREATOR_ID]


def save_admins(admin_list: list):
    """Сохраняет список админов"""
    try:
        with open(ADMINS_FILE, 'w') as f:
            json.dump(admin_list, f, indent=2)
    except Exception as e:
        logger.error(f"Ошибка при сохранении admins.json: {e}")


def is_user_blocked(user_id: int) -> bool:
    """Проверяет, заблокирован ли юзер"""
    blocked = load_blocked_users()
    return user_id in blocked


def is_admin(user_id: int) -> bool:
    """Проверяет, админ ли юзер"""
    admins = load_admins()
    return user_id in admins


def block_user(user_id: int) -> bool:
    """Блокирует юзера"""
    blocked = load_blocked_users()
    if user_id not in blocked:
        blocked.append(user_id)
        save_blocked_users(blocked)
        logger.info(f"🚫 Юзер {user_id} заблокирован")
        return True
    return False


def unblock_user(user_id: int) -> bool:
    """Разблокирует юзера"""
    blocked = load_blocked_users()
    if user_id in blocked:
        blocked.remove(user_id)
        save_blocked_users(blocked)
        logger.info(f"✅ Юзер {user_id} разблокирован")
        return True
    return False


def add_admin(user_id: int) -> bool:
    """Добавляет админа"""
    admins = load_admins()
    if user_id not in admins:
        admins.append(user_id)
        save_admins(admins)
        logger.info(f"👑 Юзер {user_id} стал админом")
        return True
    return False


def remove_admin(user_id: int) -> bool:
    """Удаляет админа (кроме создателя)"""
    if user_id == CREATOR_ID:
        return False  # Нельзя убрать создателя

    admins = load_admins()
    if user_id in admins:
        admins.remove(user_id)
        save_admins(admins)
        logger.info(f"👑 Юзер {user_id} больше не админ")
        return True
    return False


def get_blocked_users() -> list:
    """Возвращает список всех заблокированных"""
    return load_blocked_users()


def get_admins() -> list:
    """Возвращает список всех админов"""
    return load_admins()