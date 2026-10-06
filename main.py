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

BOT_TOKEN = "ВАШ_ТОКЕН_ОТ_BOTFATHER"

# Ваш ID добавлен в список администраторов
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

# Инлайн-панель управления администратора (соответствует фото)
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
    await callback.message.edit_text("Выберите категорию для **удаления**:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("delcat_"))
async def process_del_cat(callback: types.CallbackQuery):
    cat_id = int(callback.data.split("_")[1])
    delete_category(cat_id)
    await callback.message.edit_text("✅ Категория удалена.")

# --- ДОБАВЛЕНИЕ ТОВАРА ---

@dp.callback_query(F.data == "admin_add_product")
async def start_add_product(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMINS: return
    cats = get_categories()
    buttons = [[InlineKeyboardButton(text=name, callback_data=f"addprodcat_{cid}")] for cid, name in cats]
    await callback.message.edit_text("Выберите категорию для нового товара:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AdminSG.add_prod_cat)

@dp.callback_query(F.data.startswith("addprodcat_"), AdminSG.add_prod_cat)
async def process_prod_cat(callback: types.CallbackQuery, state: FSMContext):
    cat_id = int(callback.data.split("_")[1])
    await state.update_data(category_id=cat_id)
    await callback.message.edit_text("Введите **название товара**:")
    await state.set_state(AdminSG.add_prod_name)

@dp.message(AdminSG.add_prod_name)
async def process_prod_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите **описание товара**:")
    await state.set_state(AdminSG.add_prod_desc)

@dp.message(AdminSG.add_prod_desc)
async def process_prod_desc(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("Введите **цену товара** (числом):")
    await state.set_state(AdminSG.add_prod_price)

@dp.message(AdminSG.add_prod_price)
async def process_prod_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text)
        await state.update_data(price=price)
        await message.answer("Отправьте **фотографию товара**:")
        await state.set_state(AdminSG.add_prod_photo)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число.")

@dp.message(AdminSG.add_prod_photo, F.photo)
async def process_prod_photo(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    data = await state.get_data()
    add_product_to_db(data['category_id'], data['name'], data['description'], data['price'], photo_id)
    await message.answer(f"✅ Товар **{data['name']}** добавлен в каталог!", parse_mode="Markdown")
    await state.clear()

# --- ВЫДАЧА БАЛАНСА ---

@dp.callback_query(F.data == "admin_give_balance")
async def start_give_balance(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMINS: return
    await callback.message.edit_text("Введите Telegram ID пользователя:")
    await state.set_state(AdminSG.give_balance_user)

@dp.message(AdminSG.give_balance_user)
async def process_gb_user(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        await state.update_data(target_user=int(message.text))
        await message.answer("Введите сумму пополнения (в рублях):")
        await state.set_state(AdminSG.give_balance_amount)
    else:
        await message.answer("Введите числовой Telegram ID.")

@dp.message(AdminSG.give_balance_amount)
async def process_gb_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        data = await state.get_data()
        update_user_balance(data['target_user'], amount)
        await message.answer(f"✅ Пользователю `{data['target_user']}` начислено `{amount}` руб.", parse_mode="Markdown")
        await state.clear()
    except ValueError:
        await message.answer("Введите корректную сумму.")

# --- РАССЫЛКА ---

@dp.callback_query(F.data == "admin_broadcast")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMINS: return
    await callback.message.edit_text("Введите текст сообщения для рассылки всем пользователям:")
    await state.set_state(AdminSG.broadcast_msg)

@dp.message(AdminSG.broadcast_msg)
async def process_broadcast(message: types.Message, state: FSMContext):
    users = get_all_users_ids()
    count = 0
    for uid in users:
        try:
            await bot.send_message(uid, message.text)
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await message.answer(f"📢 Рассылка завершена. Успешно отправлено: **{count}** пользователям.", parse_mode="Markdown")
    await state.clear()

# --- СТАТИСТИКА И ПОИСК ---

@dp.callback_query(F.data.in_({"admin_stats", "admin_stats_day"}))
async def show_stats(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS: return
    await callback.answer("📊 Статистика: Заказов — 0, Выручка — 0 руб.", show_alert=True)

@dp.callback_query(F.data == "admin_search_info")
async def search_info(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMINS: return
    await callback.message.edit_text("Введите ID пользователя для поиска:")
    await state.set_state(AdminSG.search_user_id)

@dp.message(AdminSG.search_user_id)
async def process_search(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        user = get_user_info(int(message.text))
        if user:
            await message.answer(f"👤 **Информация:**\nID: `{user[0]}`\nБаланс: `{user[2]}` руб.\nКурьер: {'Да' if user[3] else 'Нет'}", parse_mode="Markdown")
        else:
            await message.answer("Пользователь не найден в БД.")
        await state.clear()

async def main():
    logging.basicConfig(level=logging.INFO)
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
