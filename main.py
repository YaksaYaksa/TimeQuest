import json
import asyncio
import logging
import random
from collections import Counter
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import TimedOut, BadRequest

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Хранение данных
DATA_FILE = "data.json"
users = {}

def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(users, f)

# Динамическое главное меню
def get_main_menu(user_id):
    if user_id not in users:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Создать героя", callback_data="create")],
            [InlineKeyboardButton("Новая миссия", callback_data="quest"), InlineKeyboardButton("Инвентарь", callback_data="inventory")],
            [InlineKeyboardButton("Карта", callback_data="map"), InlineKeyboardButton("Статус", callback_data="status")],
            [InlineKeyboardButton("Отдых", callback_data="rest"), InlineKeyboardButton("Магазин", callback_data="shop")],
            [InlineKeyboardButton("Сразиться", callback_data="fight"), InlineKeyboardButton("Описание бота", callback_data="description")]
        ])
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Редактировать героя", callback_data="edit_hero")],
            [InlineKeyboardButton("Новая миссия", callback_data="quest"), InlineKeyboardButton("Инвентарь", callback_data="inventory")],
            [InlineKeyboardButton("Карта", callback_data="map"), InlineKeyboardButton("Статус", callback_data="status")],
            [InlineKeyboardButton("Отдых", callback_data="rest"), InlineKeyboardButton("Магазин", callback_data="shop")],
            [InlineKeyboardButton("Сразиться", callback_data="fight"), InlineKeyboardButton("Описание бота", callback_data="description")]
        ])

# Инлайн-клавиатура для выбора класса
CLASS_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("Knight", callback_data="class_Knight"), InlineKeyboardButton("Mage", callback_data="class_Mage"), InlineKeyboardButton("Explorer", callback_data="class_Explorer")]
])

# Инлайн-клавиатура для выбора сложности
DIFFICULTY_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("Easy (15 мин)", callback_data="difficulty_Easy")],
    [InlineKeyboardButton("Medium (30 мин)", callback_data="difficulty_Medium")],
    [InlineKeyboardButton("Hard (60 мин)", callback_data="difficulty_Hard")]
])

# Инлайн-клавиатура для магазина
SHOP_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("Зелье энергии (50 монет)", callback_data="buy_potion")],
    [InlineKeyboardButton("Супер-меч (100 монет)", callback_data="buy_super_sword")],
    [InlineKeyboardButton("Назад", callback_data="back_to_menu")]
])

# Текстовая клавиатура с кнопкой "Показать меню"
SHOW_MENU_KEYBOARD = ReplyKeyboardMarkup([[KeyboardButton("Показать меню")]], resize_keyboard=True, one_time_keyboard=False)

# Функция для отправки сообщения с повторными попытками
async def send_with_retry(bot, chat_id, text, reply_markup=None, parse_mode=None, retries=3, delay=1):
    for attempt in range(retries):
        try:
            logger.info(f"Попытка {attempt + 1} отправить сообщение: {text[:50]}...")
            msg = await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
            logger.info("Сообщение успешно отправлено.")
            return msg
        except TimedOut as e:
            logger.warning(f"Тайм-аут на попытке {attempt + 1}: {str(e)}")
            if attempt < retries - 1:
                await asyncio.sleep(delay)
            else:
                logger.error("Все попытки исчерпаны при отправке сообщения.")
                return None

# Функция для редактирования сообщения с повторными попытками
async def edit_with_retry(bot, chat_id, message_id, text, reply_markup=None, parse_mode=None, retries=3, delay=1):
    for attempt in range(retries):
        try:
            logger.info(f"Попытка {attempt + 1} отредактировать сообщение: {text[:50]}...")
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
            logger.info("Сообщение успешно отредактировано.")
            return True
        except BadRequest as e:
            if "Message is not modified" in str(e):
                logger.debug(f"Сообщение не изменено, пропускаем обновление: {text[:50]}")
                return True
            logger.warning(f"BadRequest на попытке {attempt + 1}: {str(e)}")
            if attempt < retries - 1:
                await asyncio.sleep(delay)
            else:
                logger.error("Не удалось отредактировать сообщение после всех попыток.")
                return False
        except TimedOut as e:
            logger.warning(f"Тайм-аут на попытке {attempt + 1}: {str(e)}")
            if attempt < retries - 1:
                await asyncio.sleep(delay)
            else:
                logger.error("Не удалось отредактировать сообщение после всех попыток.")
                return False

# Функция для отправки фото с повторными попытками
async def send_photo_with_retry(bot, chat_id, photo, caption=None, reply_markup=None, retries=3, delay=1):
    for attempt in range(retries):
        try:
            logger.info(f"Попытка {attempt + 1} отправить фото в чат {chat_id}...")
            msg = await bot.send_photo(chat_id=chat_id, photo=photo, caption=caption, reply_markup=reply_markup)
            logger.info("Фото успешно отправлено.")
            return msg
        except TimedOut as e:
            logger.warning(f"Тайм-аут на попытке {attempt + 1}: {str(e)}")
            if attempt < retries - 1:
                await asyncio.sleep(delay)
            else:
                logger.error("Все попытки отправки фото исчерпаны.")
                return None

# Команда /start с локальным изображением
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    chat_id = update.message.chat_id
    
    welcome_text = (
        "🌟 TimeQuest: Твой помощник в борьбе с прокрастинацией! 🌟\n\n"
        "Я — бот-тайм-менеджер с элементами RPG, созданный, чтобы превратить твои задачи в увлекательные квесты! "
        "Здесь ты можешь создать героя, выполнять миссии, сражаться с монстрами, зарабатывать опыт и монеты, "
        "открывать новые регионы и становиться мастером своего времени. "
        "Моя цель — помочь тебе справляться с делами и побеждать лень через игру!\n\n"
        "✨ Что дальше? Выбери действие ниже:"
    )
    
    welcome_image_path = r"C:\Users\home\Desktop\tq\welcome_image.png"
    with open(welcome_image_path, "rb") as photo_file:
        msg = await send_photo_with_retry(
            context.bot,
            chat_id,
            photo=photo_file,
            caption=welcome_text,
            reply_markup=get_main_menu(user_id)
        )
    if msg:
        context.user_data["last_message_id"] = msg.message_id

# Описание бота
async def description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    last_message_id = context.user_data.get("last_message_id")
    
    full_description = (
        "🌟 *TimeQuest: Полное руководство по твоему приключению!* 🌟\n\n"
        "TimeQuest — это бот-тайм-менеджер с элементами RPG, который превращает твои задачи в квесты и даёт возможность сражаться с монстрами. Вот как это работает:\n\n"
        "📜 *Основные механики:*\n"
        "- *Герой*: Создай своего персонажа (рыцарь, маг или исследователь).\n"
        "- *Квесты*: Задачи — это миссии с таймером (15, 30 или 60 минут).\n"
        "- *Сражения*: Сражайся с монстрами, трать энергию и получай награды.\n"
        "- *Прогресс*: Получай опыт, монеты и открывай регионы (Лес → Горы → Замок).\n"
        "- *Энергия*: Квесты и бои тратят энергию (15-60), восстанавливай через отдых.\n"
        "- *Инвентарь*: Собирай награды (например, 'Меч').\n\n"
        "🎮 *Функции (кнопки меню):*\n"
        "1. *Создать героя* — Введи имя и выбери класс (только если героя нет).\n"
        "2. *Редактировать героя* — Измени имя и класс героя.\n"
        "3. *Новая миссия* — Задача с таймером.\n"
        "4. *Инвентарь* — Посмотри предметы.\n"
        "5. *Карта* — Текущий регион.\n"
        "6. *Статус* — Характеристики героя.\n"
        "7. *Отдых* — Напиши 'готово' 5 раз для +20 энергии.\n"
        "8. *Магазин* — Купи предметы за монеты.\n"
        "9. *Сразиться* — Бой с монстрами за награды.\n"
        "10. *Описание бота* — Читай это!\n\n"
        "⚙️ *Как использовать:*\n"
        "- Нажми кнопку и следуй инструкциям.\n"
        "- Квесты: Easy (15), Medium (30), Hard (60) энергии.\n"
        "- За квест: опыт (10/25/50), 10 монет, уровень за 10 опыта.\n\n"
        "🏅 *Цель*: Дойди до Замка и победи прокрастинацию!"
    )
    
    if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, full_description, reply_markup=get_main_menu(user_id), parse_mode="Markdown"):
        return
    msg = await send_with_retry(context.bot, chat_id, full_description, reply_markup=get_main_menu(user_id), parse_mode="Markdown")
    if msg:
        context.user_data["last_message_id"] = msg.message_id

# Создание героя
async def create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    last_message_id = context.user_data.get("last_message_id")
    
    await query.answer()
    
    if user_id in users:
        if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "У тебя уже есть герой! Используй 'Статус' или 'Редактировать героя'.", reply_markup=get_main_menu(user_id)):
            return
        msg = await send_with_retry(context.bot, chat_id, "У тебя уже есть герой! Используй 'Статус' или 'Редактировать героя'.", reply_markup=get_main_menu(user_id))
        if msg:
            context.user_data["last_message_id"] = msg.message_id
        return
    
    if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "Введи имя героя:", reply_markup=CLASS_MENU):
        pass
    else:
        msg = await send_with_retry(context.bot, chat_id, "Введи имя героя:", reply_markup=CLASS_MENU)
        if msg:
            context.user_data["last_message_id"] = msg.message_id
    context.user_data["awaiting_create_name"] = True

# Редактирование героя
async def edit_hero(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    last_message_id = context.user_data.get("last_message_id")
    
    await query.answer()
    
    if user_id not in users:
        if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "Сначала создай героя!", reply_markup=get_main_menu(user_id)):
            return
        msg = await send_with_retry(context.bot, chat_id, "Сначала создай героя!", reply_markup=get_main_menu(user_id))
        if msg:
            context.user_data["last_message_id"] = msg.message_id
        return
    
    if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "Введи новое имя героя:", reply_markup=CLASS_MENU):
        pass
    else:
        msg = await send_with_retry(context.bot, chat_id, "Введи новое имя героя:", reply_markup=CLASS_MENU)
        if msg:
            context.user_data["last_message_id"] = msg.message_id
    context.user_data["awaiting_edit_name"] = True

# Новая миссия
async def quest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    last_message_id = context.user_data.get("last_message_id")
    
    await query.answer()
    
    if user_id not in users:
        if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "Сначала создай героя!", reply_markup=get_main_menu(user_id)):
            return
        msg = await send_with_retry(context.bot, chat_id, "Сначала создай героя!", reply_markup=get_main_menu(user_id))
        if msg:
            context.user_data["last_message_id"] = msg.message_id
        return
    if users[user_id]["current_quest"]:
        if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "У тебя уже есть квест!", reply_markup=get_main_menu(user_id)):
            return
        msg = await send_with_retry(context.bot, chat_id, "У тебя уже есть квест!", reply_markup=get_main_menu(user_id))
        if msg:
            context.user_data["last_message_id"] = msg.message_id
        return
    
    if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "Введи задачу (например, 'Написать код'):", reply_markup=SHOW_MENU_KEYBOARD):
        pass
    else:
        msg = await send_with_retry(context.bot, chat_id, "Введи задачу (например, 'Написать код'):", reply_markup=SHOW_MENU_KEYBOARD)
        if msg:
            context.user_data["last_message_id"] = msg.message_id
    context.user_data["awaiting_quest_text"] = True

# Инвентарь
async def inventory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    last_message_id = context.user_data.get("last_message_id")
    
    await query.answer()
    logger.info(f"Кнопка 'Инвентарь' нажата пользователем {user_id}")
    
    if user_id not in users:
        if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "Сначала создай героя!", reply_markup=get_main_menu(user_id)):
            return
        msg = await send_with_retry(context.bot, chat_id, "Сначала создай героя!", reply_markup=get_main_menu(user_id))
        if msg:
            context.user_data["last_message_id"] = msg.message_id
        return
    items = users[user_id]["inventory"]
    if not items:
        msg_text = "Инвентарь: Пусто"
    else:
        item_counts = Counter(items)
        msg_text = "Инвентарь:\n" + "\n".join(f"{item} - {count} шт." for item, count in item_counts.items())
    
    if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, msg_text, reply_markup=get_main_menu(user_id)):
        return
    msg = await send_with_retry(context.bot, chat_id, msg_text, reply_markup=get_main_menu(user_id))
    if msg:
        context.user_data["last_message_id"] = msg.message_id

# Карта
async def map(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    last_message_id = context.user_data.get("last_message_id")
    
    await query.answer()
    logger.info(f"Кнопка 'Карта' нажата пользователем {user_id}")
    
    if user_id not in users:
        if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "Сначала создай героя!", reply_markup=get_main_menu(user_id)):
            return
        msg = await send_with_retry(context.bot, chat_id, "Сначала создай героя!", reply_markup=get_main_menu(user_id))
        if msg:
            context.user_data["last_message_id"] = msg.message_id
        return
    region = ["Лес", "Горы", "Замок"][users[user_id]["region"]]
    
    if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, f"Текущий регион: {region}", reply_markup=get_main_menu(user_id)):
        return
    msg = await send_with_retry(context.bot, chat_id, f"Текущий регион: {region}", reply_markup=get_main_menu(user_id))
    if msg:
        context.user_data["last_message_id"] = msg.message_id

# Статус
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    last_message_id = context.user_data.get("last_message_id")
    
    await query.answer()
    logger.info(f"Кнопка 'Статус' нажата пользователем {user_id}")
    
    if user_id not in users:
        if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "Сначала создай героя!", reply_markup=get_main_menu(user_id)):
            return
        msg = await send_with_retry(context.bot, chat_id, "Сначала создай героя!", reply_markup=get_main_menu(user_id))
        if msg:
            context.user_data["last_message_id"] = msg.message_id
        return
    user = users[user_id]
    msg_text = (
        f"Герой: {user['name']} ({user['class']})\n"
        f"Уровень: {user['level']}\n"
        f"Опыт: {user['exp']}\n"
        f"Монеты: {user['coins']}\n"
        f"Энергия: {user['energy']}\n"
        f"Регион: {['Лес', 'Горы', 'Замок'][user['region']]}"
    )
    
    if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, msg_text, reply_markup=get_main_menu(user_id)):
        return
    msg = await send_with_retry(context.bot, chat_id, msg_text, reply_markup=get_main_menu(user_id))
    if msg:
        context.user_data["last_message_id"] = msg.message_id

# Магазин
async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    last_message_id = context.user_data.get("last_message_id")
    
    await query.answer()
    logger.info(f"Кнопка 'Магазин' нажата пользователем {user_id}")
    
    if user_id not in users:
        if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "Сначала создай героя!", reply_markup=get_main_menu(user_id)):
            return
        msg = await send_with_retry(context.bot, chat_id, "Сначала создай героя!", reply_markup=get_main_menu(user_id))
        if msg:
            context.user_data["last_message_id"] = msg.message_id
        return
    
    shop_text = (
        f"Добро пожаловать в магазин, {users[user_id]['name']}!\n"
        f"Твои монеты: {users[user_id]['coins']}\n\n"
        "Что хочешь купить?\n"
        "- Зелье энергии (+20 энергии) — 50 монет\n"
        "- Супер-меч (в инвентарь) — 100 монет"
    )
    
    if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, shop_text, reply_markup=SHOP_MENU):
        return
    msg = await send_with_retry(context.bot, chat_id, shop_text, reply_markup=SHOP_MENU)
    if msg:
        context.user_data["last_message_id"] = msg.message_id

# Сражение с монстрами
async def fight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    last_message_id = context.user_data.get("last_message_id")
    
    await query.answer()
    logger.info(f"Кнопка 'Сразиться' нажата пользователем {user_id}")
    
    if user_id not in users:
        if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "Сначала создай героя!", reply_markup=get_main_menu(user_id)):
            return
        msg = await send_with_retry(context.bot, chat_id, "Сначала создай героя!", reply_markup=get_main_menu(user_id))
        if msg:
            context.user_data["last_message_id"] = msg.message_id
        return
    
    monsters = [
        ("Гоблин", 10, 70, (5, 5, None)),
        ("Орк", 20, 50, (15, 10, None)),
        ("Дракон", 40, 30, (50, 25, "Драконий клык" if random.random() < 0.3 else None))
    ]
    monster = random.choice(monsters)
    monster_name, energy_cost, base_win_chance, (coins_reward, exp_reward, item_reward) = monster
    
    if users[user_id]["energy"] < energy_cost:
        if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, f"Недостаточно энергии ({users[user_id]['energy']}/{energy_cost})! Используй 'Отдых' или магазин.", reply_markup=get_main_menu(user_id)):
            return
        msg = await send_with_retry(context.bot, chat_id, f"Недостаточно энергии ({users[user_id]['energy']}/{energy_cost})! Используй 'Отдых' или магазин.", reply_markup=get_main_menu(user_id))
        if msg:
            context.user_data["last_message_id"] = msg.message_id
        return
    
    win_chance = min(95, base_win_chance + 5 * (users[user_id]["level"] - 1))
    users[user_id]["energy"] -= energy_cost
    fight_result = random.random() * 100 < win_chance
    
    if fight_result:
        users[user_id]["coins"] += coins_reward
        users[user_id]["exp"] += exp_reward
        if item_reward:
            users[user_id]["inventory"].append(item_reward)
        save_data()
        result_text = (
            f"Ты сразился с {monster_name} и победил!\n"
            f"Награда: +{coins_reward} монет, +{exp_reward} опыта"
            f"{', ' + item_reward + ' в инвентарь' if item_reward else ''}."
        )
    else:
        save_data()
        result_text = f"Ты сразился с {monster_name} и проиграл! Энергия потрачена, попробуй ещё раз."
    
    if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, result_text, reply_markup=get_main_menu(user_id)):
        return
    msg = await send_with_retry(context.bot, chat_id, result_text, reply_markup=get_main_menu(user_id))
    if msg:
        context.user_data["last_message_id"] = msg.message_id

# Функция отдыха
async def rest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = str(update.effective_user.id)
    last_message_id = context.user_data.get("last_message_id")
    
    await query.answer()
    logger.info(f"Кнопка 'Отдых' нажата пользователем {user_id}")
    
    if user_id not in users:
        if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "Сначала создай героя!", reply_markup=get_main_menu(user_id)):
            return
        msg = await send_with_retry(context.bot, chat_id, "Сначала создай героя!", reply_markup=get_main_menu(user_id))
        if msg:
            context.user_data["last_message_id"] = msg.message_id
        return
    if "rest_count" in context.user_data:
        if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, f"Ты уже отдыхаешь! Напиши 'готово' ещё {5 - context.user_data['rest_count']} раз.", reply_markup=get_main_menu(user_id)):
            return
        msg = await send_with_retry(context.bot, chat_id, f"Ты уже отдыхаешь! Напиши 'готово' ещё {5 - context.user_data['rest_count']} раз.", reply_markup=get_main_menu(user_id))
        if msg:
            context.user_data["last_message_id"] = msg.message_id
        return
    
    if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "Твой герой устал! Напиши 'готово' 5 раз для восстановления энергии.", reply_markup=SHOW_MENU_KEYBOARD):
        pass
    else:
        msg = await send_with_retry(context.bot, chat_id, "Твой герой устал! Напиши 'готово' 5 раз для восстановления энергии.", reply_markup=SHOW_MENU_KEYBOARD)
        if msg:
            context.user_data["last_message_id"] = msg.message_id
    context.user_data["rest_count"] = 0

# Обработка текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()
    chat_id = update.message.chat_id
    last_message_id = context.user_data.get("last_message_id")

    logger.info(f"Получено текстовое сообщение от {user_id}: {text}")

    if text == "Показать меню":
        if users.get(user_id, {}).get("current_quest"):
            quest = users[user_id]["current_quest"]
            elapsed = asyncio.get_event_loop().time() - context.user_data.get("quest_start_time", asyncio.get_event_loop().time())
            total_seconds = quest["time"] * 60
            remaining = total_seconds - elapsed
            progress_percent = min(100, int((elapsed / total_seconds) * 100))
            bar_length = 10
            filled = int(bar_length * progress_percent / 100)
            bar = "█" * filled + " " * (bar_length - filled)
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            time_str = f"{minutes:02d}:{seconds:02d}"
            progress_text = f"Квест: {quest['title']}\nОсталось: {time_str}\nПрогресс: [{bar}] {progress_percent}%"
            msg = await send_with_retry(context.bot, chat_id, progress_text, reply_markup=get_main_menu(user_id))
            if msg:
                context.user_data["last_message_id"] = msg.message_id
        else:
            msg = await send_with_retry(context.bot, chat_id, "Выбери действие:", reply_markup=get_main_menu(user_id))
            if msg:
                context.user_data["last_message_id"] = msg.message_id
        return
    
    if context.user_data.get("awaiting_create_name"):
        context.user_data["hero_name"] = text
        context.user_data["awaiting_create_name"] = False
        if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, f"Имя: {text}\nВыбери класс:", reply_markup=CLASS_MENU):
            return
        msg = await send_with_retry(context.bot, chat_id, f"Имя: {text}\nВыбери класс:", reply_markup=CLASS_MENU)
        if msg:
            context.user_data["last_message_id"] = msg.message_id
        return
    
    if context.user_data.get("awaiting_edit_name"):
        context.user_data["hero_name"] = text
        context.user_data["awaiting_edit_name"] = False
        if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, f"Новое имя: {text}\nВыбери новый класс:", reply_markup=CLASS_MENU):
            return
        msg = await send_with_retry(context.bot, chat_id, f"Новое имя: {text}\nВыбери новый класс:", reply_markup=CLASS_MENU)
        if msg:
            context.user_data["last_message_id"] = msg.message_id
        return
    
    if context.user_data.get("awaiting_quest_text"):
        context.user_data["quest_text"] = text
        context.user_data["awaiting_quest_text"] = False
        if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "Выбери сложность квеста:", reply_markup=DIFFICULTY_MENU):
            return
        msg = await send_with_retry(context.bot, chat_id, "Выбери сложность квеста:", reply_markup=DIFFICULTY_MENU)
        if msg:
            context.user_data["last_message_id"] = msg.message_id
        return
    
    if "rest_count" in context.user_data:
        if text.lower() == "готово":
            context.user_data["rest_count"] += 1
            if context.user_data["rest_count"] >= 5:
                users[user_id]["energy"] = min(100, users[user_id]["energy"] + 20)
                if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, f"Травы собраны! Энергия: {users[user_id]['energy']}", reply_markup=get_main_menu(user_id)):
                    del context.user_data["rest_count"]
                    return
                msg = await send_with_retry(context.bot, chat_id, f"Травы собраны! Энергия: {users[user_id]['energy']}", reply_markup=get_main_menu(user_id))
                if msg:
                    context.user_data["last_message_id"] = msg.message_id
                del context.user_data["rest_count"]
            else:
                remaining = 5 - context.user_data["rest_count"]
                rest_messages = [
                    f"Ещё {remaining} трав, и герой скажет 'Уф, устал!' Пиши 'готово'!",
                    f"Собери ещё {remaining} трав, не ленись, как дракон! 'Готово' в помощь.",
                    f"Осталось {remaining} трав до эпичного отдыха, давай 'готово'!",
                    f"Герой просит ещё {remaining} трав, пиши 'готово', не зевай!",
                    f"Травы ждут: ещё {remaining} раз 'готово', и ты мастер отдыха!",
                    f"Ещё {remaining} трав до победы над усталостью, пиши 'готово'!",
                    f"Только {remaining} трав отделяют тебя от релакса, давай 'готово'!",
                    f"Собери ещё {remaining} трав, или герой начнёт ныть! Пиши 'готово'.",
                    f"Осталось {remaining} трав — 'готово', и энергия в кармане!",
                    f"Ещё {remaining} 'готово', и травы скажут тебе спасибо!"
                ]
                if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, random.choice(rest_messages), reply_markup=SHOW_MENU_KEYBOARD):
                    return
                msg = await send_with_retry(context.bot, chat_id, random.choice(rest_messages), reply_markup=SHOW_MENU_KEYBOARD)
                if msg:
                    context.user_data["last_message_id"] = msg.message_id
        else:
            error_messages = [
                "Эй, это не заклинание 'готово'! Попробуй ещё раз.",
                "Ну ты даёшь! Герои так не пишут, давай 'готово'!",
                "Что-то твои травы не собрались, пиши 'готово' точнее!",
                "Твой герой в шоке: это не 'готово', пробуй снова!",
                "Ой, не туда пальцем попал! Пиши 'готово', чемпион.",
                "Травы смеются над тобой! Давай 'готово' как надо.",
                "Не-а, это не пароль от сокровищ! Пиши 'готово'.",
                "Герой устал от ошибок, давай 'готово' без фокусов!",
                "Ты что, траву пугаешь? Пиши 'готово', не стесняйся.",
                "Это не эпичное заклинание! 'Готово' — вот что нужно."
            ]
            if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, random.choice(error_messages), reply_markup=SHOW_MENU_KEYBOARD):
                return
            msg = await send_with_retry(context.bot, chat_id, random.choice(error_messages), reply_markup=SHOW_MENU_KEYBOARD)
            if msg:
                context.user_data["last_message_id"] = msg.message_id

# Функция для обновления прогресс-бара квеста
async def update_quest_progress(bot, chat_id, message_id, title, total_time, user_id, context):
    start_time = asyncio.get_event_loop().time()
    context.user_data["quest_start_time"] = start_time
    update_interval = 5
    total_seconds = total_time * 60
    
    logger.info(f"Запущено обновление прогресс-бара для квеста '{title}' (user_id: {user_id})")
    
    last_progress_text = ""
    
    while True:
        elapsed = asyncio.get_event_loop().time() - start_time
        remaining = total_seconds - elapsed
        
        if remaining <= 0:
            logger.info(f"Прогресс-бар для квеста '{title}' завершён (user_id: {user_id})")
            break
        
        progress_percent = min(100, int((elapsed / total_seconds) * 100))
        bar_length = 10
        filled = int(bar_length * progress_percent / 100)
        bar = "█" * filled + " " * (bar_length - filled)
        
        minutes = int(remaining // 60)
        seconds = int(remaining % 60)
        time_str = f"{minutes:02d}:{seconds:02d}"
        
        progress_text = f"Квест: {title}\nОсталось: {time_str}\nПрогресс: [{bar}] {progress_percent}%"
        
        if progress_text != last_progress_text:
            await edit_with_retry(bot, chat_id, message_id, progress_text)
            last_progress_text = progress_text
        
        await asyncio.sleep(update_interval)

# Обработка callback-запросов от инлайн-кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id
    user_id = str(query.from_user.id)
    last_message_id = context.user_data.get("last_message_id")
    
    logger.info(f"Получен callback от {user_id}: {data}")
    
    await query.answer()
    
    if data == "create":
        await create(update, context)
    elif data == "edit_hero":
        await edit_hero(update, context)
    elif data.startswith("class_"):
        class_name = data.split("_")[1]
        if context.user_data.get("hero_name"):
            name = context.user_data["hero_name"]
            if "awaiting_create_name" in context.user_data:
                del context.user_data["awaiting_create_name"]
                users[user_id] = {
                    "name": name,
                    "class": class_name,
                    "level": 1,
                    "exp": 0,
                    "coins": 0,
                    "energy": 100,
                    "inventory": [],
                    "region": 0,
                    "quests_completed": 0,
                    "current_quest": None
                }
                save_data()
                del context.user_data["hero_name"]
                if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, f"Герой {name} ({class_name}) создан!", reply_markup=get_main_menu(user_id)):
                    return
                msg = await send_with_retry(context.bot, chat_id, f"Герой {name} ({class_name}) создан!", reply_markup=get_main_menu(user_id))
                if msg:
                    context.user_data["last_message_id"] = msg.message_id
            elif "awaiting_edit_name" in context.user_data:
                del context.user_data["awaiting_edit_name"]
                users[user_id]["name"] = name
                users[user_id]["class"] = class_name
                save_data()
                del context.user_data["hero_name"]
                if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, f"Герой изменён: {name} ({class_name})!", reply_markup=get_main_menu(user_id)):
                    return
                msg = await send_with_retry(context.bot, chat_id, f"Герой изменён: {name} ({class_name})!", reply_markup=get_main_menu(user_id))
                if msg:
                    context.user_data["last_message_id"] = msg.message_id
        return
    elif data == "quest":
        await quest(update, context)
    elif data == "inventory":
        await inventory(update, context)
    elif data == "map":
        await map(update, context)
    elif data == "status":
        await status(update, context)
    elif data == "rest":
        await rest(update, context)
    elif data == "shop":
        await shop(update, context)
    elif data == "fight":
        await fight(update, context)
    elif data == "description":
        await description(update, context)
    elif data == "buy_potion":
        if user_id not in users:
            if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "Сначала создай героя!", reply_markup=get_main_menu(user_id)):
                return
            msg = await send_with_retry(context.bot, chat_id, "Сначала создай героя!", reply_markup=get_main_menu(user_id))
            if msg:
                context.user_data["last_message_id"] = msg.message_id
            return
        if users[user_id]["coins"] < 50:
            if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "Недостаточно монет! Завершай квесты.", reply_markup=SHOP_MENU):
                return
            msg = await send_with_retry(context.bot, chat_id, "Недостаточно монет! Завершай квесты.", reply_markup=SHOP_MENU)
            if msg:
                context.user_data["last_message_id"] = msg.message_id
        else:
            users[user_id]["coins"] -= 50
            users[user_id]["energy"] = min(100, users[user_id]["energy"] + 20)
            save_data()
            if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "Зелье энергии куплено! Энергия +20.", reply_markup=SHOP_MENU):
                return
            msg = await send_with_retry(context.bot, chat_id, "Зелье энергии куплено! Энергия +20.", reply_markup=SHOP_MENU)
            if msg:
                context.user_data["last_message_id"] = msg.message_id
    elif data == "buy_super_sword":
        if user_id not in users:
            if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "Сначала создай героя!", reply_markup=get_main_menu(user_id)):
                return
            msg = await send_with_retry(context.bot, chat_id, "Сначала создай героя!", reply_markup=get_main_menu(user_id))
            if msg:
                context.user_data["last_message_id"] = msg.message_id
            return
        if users[user_id]["coins"] < 100:
            if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "Недостаточно монет! Завершай квесты.", reply_markup=SHOP_MENU):
                return
            msg = await send_with_retry(context.bot, chat_id, "Недостаточно монет! Завершай квесты.", reply_markup=SHOP_MENU)
            if msg:
                context.user_data["last_message_id"] = msg.message_id
        else:
            users[user_id]["coins"] -= 100
            users[user_id]["inventory"].append("Супер-меч")
            save_data()
            if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "Супер-меч куплен! Проверь инвентарь.", reply_markup=SHOP_MENU):
                return
            msg = await send_with_retry(context.bot, chat_id, "Супер-меч куплен! Проверь инвентарь.", reply_markup=SHOP_MENU)
            if msg:
                context.user_data["last_message_id"] = msg.message_id
    elif data == "back_to_menu":
        if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "Выбери действие:", reply_markup=get_main_menu(user_id)):
            return
        msg = await send_with_retry(context.bot, chat_id, "Выбери действие:", reply_markup=get_main_menu(user_id))
        if msg:
            context.user_data["last_message_id"] = msg.message_id
    elif data.startswith("difficulty_"):
        difficulty = data.split("_")[1]
        description_text = context.user_data.get("quest_text", "Безымянная задача")
        time = {"Easy": 15, "Medium": 30, "Hard": 60}[difficulty]
        exp = {"Easy": 10, "Medium": 25, "Hard": 50}[difficulty]
        title = f"Победить дракона {description_text}"
        
        if users[user_id]["energy"] < time:
            if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, f"Недостаточно энергии ({users[user_id]['energy']}/{time})! Используй 'Отдых'.", reply_markup=get_main_menu(user_id)):
                return
            msg = await send_with_retry(context.bot, chat_id, f"Недостаточно энергии ({users[user_id]['energy']}/{time})! Используй 'Отдых'.", reply_markup=get_main_menu(user_id))
            if msg:
                context.user_data["last_message_id"] = msg.message_id
            return
        
        users[user_id]["current_quest"] = {"title": title, "time": time, "exp": exp}
        users[user_id]["energy"] -= time
        
        initial_text = f"Квест: {title}\nОсталось: {time:02d}:00\nПрогресс: [          ] 0%"
        msg = await send_with_retry(context.bot, chat_id, initial_text)
        if msg:
            context.user_data["last_message_id"] = msg.message_id
            logger.info(f"Создан квест '{title}' для user_id {user_id}, message_id: {msg.message_id}")
            asyncio.create_task(update_quest_progress(context.bot, chat_id, msg.message_id, title, time, user_id, context))
        
        total_seconds = time * 60  # Для реального времени
        # total_seconds = time  # Uncomment for testing
        await asyncio.sleep(total_seconds)
        if users[user_id]["current_quest"]:
            users[user_id]["exp"] += exp
            users[user_id]["coins"] += 10
            users[user_id]["quests_completed"] += 1
            msg = [f"Победа! +{exp} опыта, +10 монет"]
            if users[user_id]["exp"] >= users[user_id]["level"] * 10:
                users[user_id]["level"] += 1
                msg.append(f"Уровень повышен до {users[user_id]['level']}!")
            if users[user_id]["quests_completed"] % 5 == 0 and users[user_id]["region"] < 2:
                users[user_id]["region"] += 1
                msg.append(f"Новый регион открыт: {['Лес', 'Горы', 'Замок'][users[user_id]['region']]}!")
            users[user_id]["inventory"].append("Меч")
            users[user_id]["current_quest"] = None
            save_data()
            if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "\n".join(msg), reply_markup=get_main_menu(user_id)):
                return
            msg = await send_with_retry(context.bot, chat_id, "\n".join(msg), reply_markup=get_main_menu(user_id))
            if msg:
                context.user_data["last_message_id"] = msg.message_id
    else:
        logger.warning(f"Неизвестный callback: {data}")
        if last_message_id and await edit_with_retry(context.bot, chat_id, last_message_id, "Неизвестное действие. Выбери кнопку ниже.", reply_markup=get_main_menu(user_id)):
            return
        msg = await send_with_retry(context.bot, chat_id, "Неизвестное действие. Выбери кнопку ниже.", reply_markup=get_main_menu(user_id))
        if msg:
            context.user_data["last_message_id"] = msg.message_id

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    error_msg = str(context.error)
    logger.error(f"Ошибка: {error_msg}")
    chat_id = update.effective_chat.id if update else context.error.chat_id
    
    if "Query is too old" in error_msg or "query id is invalid" in error_msg:
        logger.info("Игнорируем ошибку устаревшего запроса.")
        return
    
    await context.bot.send_message(chat_id=chat_id, text=f"Произошла ошибка: {error_msg}. Попробуй снова.")

# Главная функция
def main():
    global users
    users = load_data()
    app = Application.builder().token("7525183001:AAET8jlSxnxrldh9I5_lxxC-N7Rj3FpZ8BE").build()  # Замените на новый токен
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("create", create))
    app.add_handler(CommandHandler("edit_hero", edit_hero))
    app.add_handler(CommandHandler("quest", quest))
    app.add_handler(CommandHandler("inventory", inventory))
    app.add_handler(CommandHandler("map", map))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("rest", rest))
    app.add_handler(CommandHandler("shop", shop))
    app.add_handler(CommandHandler("fight", fight))
    app.add_handler(CommandHandler("description", description))
    app.add_error_handler(error_handler)
    
    logger.info("Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()