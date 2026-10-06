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

from database import init_db, get_categories, add_product_to_db

BOT_TOKEN = "ВАШ_ТОКЕН_ОТ_BOTFATHER"

# Твой Telegram ID уже внесен в список администраторов
ADMINS = [1979046241]  

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- FSM Состояния для добавления товара ---
class AddProductSG(StatesGroup):
    select_category = State()
    enter_name = State()
    enter_description = State()
    enter_price = State()
    send_photo = State()

# --- КЛАВИАТУРЫ ---

# Главное меню: обычные покупатели не видят админских кнопок
def get_main_menu(user_id: int):
    keyboard = [
        [KeyboardButton(text="Каталог"), KeyboardButton(text="Профиль")],
        [KeyboardButton(text="Корзина"), KeyboardButton(text="💬 Отзывы")]
    ]
    
    # Спец-кнопки открываются ТОЛЬКО для ID из списка ADMINS
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
                InlineKeyboardButton(text="✏️️ Переименовать категорию", callback_data="admin_rename_cat")
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

def categories_menu():
    categories = get_categories()
    builder = []
    row = []
    for cat_id, cat_name in categories:
        row.append(InlineKeyboardButton(text=cat_name, callback_data=f"cat_{cat_id}"))
        if len(row) == 2:
            builder.append(row)
            row = []
    if row:
        builder.append(row)
    return InlineKeyboardMarkup(inline_keyboard=builder)

# --- ОБРАБОТЧИКИ СООБЩЕНИЙ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = get_main_menu(message.from_user.id)
    await message.answer("Привет! Выберите нужный раздел:", reply_markup=kb)

@dp.message(F.text == "Каталог")
async def show_catalog(message: types.Message):
    await message.answer("Выберите категорию:", reply_markup=categories_menu())

# Панель админа по кнопке
@dp.message(F.text.contains("Админка"))
async def show_admin_panel(message: types.Message):
    if message.from_user.id in ADMINS:
        await message.answer("🔧 **Панель Степы**", reply_markup=admin_panel_keyboard(), parse_mode="Markdown")
    else:
        await message.answer("⛔ У вас нет доступа к этой панели.")

# --- ПОШАГОВЫЙ СЦЕНАРИЙ: ДОБАВЛЕНИЕ ТОВАРА ---

@dp.callback_query(F.data == "admin_add_product")
async def start_add_product(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMINS:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
        
    cats = get_categories()
    buttons = [[InlineKeyboardButton(text=name, callback_data=f"addprod_cat_{cid}")] for cid, name in cats]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text("Выберите категорию для нового товара:", reply_markup=kb)
    await state.set_state(AddProductSG.select_category)

@dp.callback_query(F.data.startswith("addprod_cat_"), AddProductSG.select_category)
async def process_cat_selected(callback: types.CallbackQuery, state: FSMContext):
    cat_id = int(callback.data.split("_")[2])
    await state.update_data(category_id=cat_id)
    
    await callback.message.edit_text("Введите **название товара**:")
    await state.set_state(AddProductSG.enter_name)

@dp.message(AddProductSG.enter_name)
async def process_product_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите **описание товара**:")
    await state.set_state(AddProductSG.enter_description)

@dp.message(AddProductSG.enter_description)
async def process_product_desc(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("Введите **цену товара** (числом в рублях):")
    await state.set_state(AddProductSG.enter_price)

@dp.message(AddProductSG.enter_price)
async def process_product_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text)
        await state.update_data(price=price)
        await message.answer("Загрузите **фотографию товара** (отправьте изображение):")
        await state.set_state(AddProductSG.send_photo)
    except ValueError:
        await message.answer("Пожалуйста, введите цену только цифрами (например, `1500`).")

@dp.message(AddProductSG.send_photo, F.photo)
async def process_product_photo(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    data = await state.get_data()
    
    add_product_to_db(
        category_id=data['category_id'],
        name=data['name'],
        description=data['description'],
        price=data['price'],
        photo_id=photo_id
    )
    
    await message.answer(f"✅ Товар **{data['name']}** успешно добавлен в каталог!", parse_mode="Markdown")
    await state.clear()

# Обработчик кнопок админки
@dp.callback_query(F.data.startswith("admin_"))
async def process_admin_callbacks(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    action = callback.data.replace("admin_", "")
    await callback.answer(f"Выбран раздел: {action}", show_alert=True)

async def main():
    logging.basicConfig(level=logging.INFO)
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
