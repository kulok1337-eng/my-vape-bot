import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton
)

from database import (
    init_db, get_categories, add_category, delete_category, rename_category,
    add_product_to_db, update_user_balance, set_courier_status, get_user_info, get_all_users_ids
)

# Указан ваш токен от BotFather
BOT_TOKEN = "8270785657:AAGSAhrPTkWnUQpkSd3SXA8E48BamvfxxIc"

# Ваш Telegram ID
ADMINS = [1979046241]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- FSM СОСТОЯНИЯ ---
class AdminSG(StatesGroup):
    add_cat_name = State()
    del_cat_select = State()
    rename_cat_select = State()
    rename_cat_new_name = State()
    
    add_prod_cat = State()
    add_prod_name = State()
    add_prod_desc = State()
    add_prod_price = State()
    add_prod_photo = State()
    
    give_balance_user = State()
    give_balance_amount = State()
    
    add_courier_user = State()
    del_courier_user = State()
    
    broadcast_msg = State()
    search_user_id = State()

# --- КЛАВИАТУРЫ ---

def get_main_menu(user_id: int):
    # Обычное меню для покупателей
    keyboard = [
        [KeyboardButton(text="Каталог"), KeyboardButton(text="Профиль")],
        [KeyboardButton(text="Корзина"), KeyboardButton(text="💬 Отзывы")]
    ]
    
    # Кнопки отображаются ТОЛЬКО администраторам
    if user_id in ADMINS:
        keyboard.append([KeyboardButton(text="📦 Доступные заказы"), KeyboardButton(text="🚚 Взятые заказы")])
        keyboard.append([KeyboardButton(text="🗄 История заказов")])
        keyboard.append([KeyboardButton(text="🔧 Админка")])
        
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

# Инлайн-панель управления администратора
def admin_panel_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📁 Добавить категорию", callback_data="admin_add_cat"),
                InlineKeyboardButton(text="🗑 Удалить категорию", callback_data="admin_del_cat")
            ],
            [
                InlineKeyboardButton(text="✏️ Переименовать категорию", callback_data="admin_rename_cat")
            ],
            [
                InlineKeyboardButton(text="📦 Добавить товар", callback_data="admin_add_product"),
                InlineKeyboardButton(text="✏️ Редактирование", callback_data="admin_edit_product")
            ],
            [
                InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
                InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")
            ],
            [
                InlineKeyboardButton(text="📈 Статистика за день", callback_data="admin_stats_day")
            ],
            [
                InlineKeyboardButton(text="👤 Назначить курьера", callback_data="admin_add_courier"),
                InlineKeyboardButton(text="👤 Разжаловать курьера", callback_data="admin_del_courier")
            ],
            [
                InlineKeyboardButton(text="🔍 Поиск / Инфо", callback_data="admin_search_info"),
                InlineKeyboardButton(text="💰 Выдать баланс", callback_data="admin_give_balance")
            ],
            [
                InlineKeyboardButton(text="🔧 Технические работы", callback_data="admin_tech_works")
            ]
        ]
    )

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = get_main_menu(message.from_user.id)
    await message.answer("Привет! Выберите нужный раздел:", reply_markup=kb)

@dp.message(F.text.contains("Админка"))
async def show_admin_panel(message: types.Message):
    if message.from_user.id in ADMINS:
        await message.answer("🔧 **Панель Степы**", reply_markup=admin_panel_keyboard(), parse_mode="Markdown")
    else:
        await message.answer("⛔ У вас нет доступа к этой панели.")

# --- УПРАВЛЕНИЕ КАТЕГОРИЯМИ ---

@dp.callback_query(F.data == "admin_add_cat")
async def start_add_cat(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMINS: return
    await callback.message.edit_text("Введите **название новой категории**:")
    await state.set_state(AdminSG.add_cat_name)

@dp.message(AdminSG.add_cat_name)
async def process_add_cat(message: types.Message, state: FSMContext):
    add_category(message.text)
    await message.answer(f"✅ Категория **{message.text}** создана!", parse_mode="Markdown")
    await state.clear()

@dp.callback_query(F.data == "admin_del_cat")
async def start_del_cat(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMINS: return
    cats = get_categories()
    buttons = [[InlineKeyboardButton(text=name, callback_data=f"delcat_{cid}")] for cid, name in cats]
