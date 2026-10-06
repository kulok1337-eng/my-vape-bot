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
    init_db, get_categories, add_category, delete_category,
    add_product_to_db, get_products_by_category,
    add_to_cart, get_user_cart, clear_user_cart,
    get_user_info
)

BOT_TOKEN = "8270785657:AAGSAhrPTkWnUQpkSd3SXA8E48BamvfxxIc"
ADMINS = [1979046241]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- FSM СОСТОЯНИЯ ---
class AdminSG(StatesGroup):
    add_cat_name = State()
    add_prod_cat = State()
    add_prod_name = State()
    add_prod_desc = State()
    add_prod_price = State()
    add_prod_photo = State()

# --- КЛАВИАТУРЫ ---

def get_main_menu(user_id: int):
    keyboard = [
        [KeyboardButton(text="Каталог"), KeyboardButton(text="Профиль")],
        [KeyboardButton(text="Корзина"), KeyboardButton(text="💬 Отзывы")]
    ]
    if user_id in ADMINS:
        keyboard.append([KeyboardButton(text="📦 Доступные заказы"), KeyboardButton(text="🚚 Взятые заказы")])
        keyboard.append([KeyboardButton(text="🗄 История заказов")])
        keyboard.append([KeyboardButton(text="🔧 Админка")])
        
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def admin_panel_keyboard():
    # Полная структура админ-панели точно как на 1 фото
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
                InlineKeyboardButton(text="🔧 Технические работы", callback_data="admin_tech_work")
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

# --- ОСНОВНЫЕ КОМАНДЫ И КНОПКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = get_main_menu(message.from_user.id)
    await message.answer("Привет! Выберите нужный раздел:", reply_markup=kb)

@dp.message(F.text == "Каталог")
async def show_catalog(message: types.Message):
    await message.answer("Выберите категорию из списка:", reply_markup=categories_menu())

@dp.message(F.text == "Профиль")
async def show_profile(message: types.Message):
    user = get_user_info(message.from_user.id)
    balance = user[2] if user else 0.0
    text = (
        f"👤 **Ваш профиль**\n\n"
        f"🆔 ID: `{message.from_user.id}`\n"
        f"💰 Баланс: `{balance}` руб."
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "Корзина")
async def show_cart(message: types.Message):
    cart_items = get_user_cart(message.from_user.id)
    if not cart_items:
        await message.answer("🛒 Ваша корзина пока пуста.")
        return
    
    total_price = 0
    text = "🛒 **Ваша корзина:**\n\n"
    for name, price, count, _ in cart_items:
        item_total = price * count
        total_price += item_total
        text += f"▪️️ **{name}** — {count} шт. x {price} руб. = **{item_total} руб.**\n"
        
    text += f"\n💳 **Итого к оплате:** {total_price} руб."
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="clear_cart")],
        [InlineKeyboardButton(text="✅ Оформить заказ", callback_data="checkout")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "clear_cart")
async def process_clear_cart(callback: types.CallbackQuery):
    clear_user_cart(callback.from_user.id)
    await callback.message.edit_text("🛒 Ваша корзина очищена.")

@dp.callback_query(F.data == "checkout")
async def process_checkout(callback: types.CallbackQuery):
    clear_user_cart(callback.from_user.id)
    await callback.message.edit_text("🎉 **Спасибо за заказ!** Менеджер свяжется с вами для уточнения деталей доставки.", parse_mode="Markdown")

@dp.message(F.text == "💬 Отзывы")
async def show_reviews(message: types.Message):
    await message.answer("💬 Раздел отзывов находится в разработке.")

# --- ОГРАНИЧЕНИЕ АДМИН-КНОПОК ---

@dp.message(F.text.in_({"📦 Доступные заказы", "🚚 Взятые заказы", "🗄 История заказов", "🔧 Админка"}))
async def handle_admin_buttons(message: types.Message):
    if message.from_user.id not in ADMINS:
        kb = get_main_menu(message.from_user.id)
        await message.answer("⛔ У вас нет доступа к этому разделу.", reply_markup=kb)
        return

    if message.text == "📦 Доступные заказы":
        await message.answer("📦 Доступных заказов пока нет.")
    elif message.text == "🚚 Взятые заказы":
        await message.answer("🚚 У вас нет активных взятых заказов.")
    elif message.text == "🗄 История заказов":
        await message.answer("🗄 История заказов пуста.")
    elif "Админка" in message.text:
        await message.answer("🔧 **Панель Степы**", reply_markup=admin_panel_keyboard(), parse_mode="Markdown")

# --- РАБОТА С КАТАЛОГОМ ---

@dp.callback_query(F.data.startswith("cat_"))
async def process_category_click(callback: types.CallbackQuery):
    cat_id = int(callback.data.split("_")[1])
    products = get_products_by_category(cat_id)
    
    if not products:
        await callback.message.answer("📦 В этой категории пока нет товаров.")
        await callback.answer()
        return

    await callback.message.answer("👇 **Список товаров в категории:**", parse_mode="Markdown")
    for prod_id, name, desc, price, photo_id in products:
        caption = f"📦 **{name}**\n\n{desc}\n\n💰 **Цена:** {price} руб."
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 В корзину", callback_data=f"buy_{prod_id}")]
        ])
        if photo_id:
            await callback.message.answer_photo(photo=photo_id, caption=caption, reply_markup=kb, parse_mode="Markdown")
        else:
            await callback.message.answer(caption, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data.startswith("buy_"))
async def process_add_to_cart(callback: types.CallbackQuery):
    prod_id = int(callback.data.split("_")[1])
    add_to_cart(callback.from_user.id, prod_id)
    await callback.answer("✅ Товар добавлен в корзину!", show_alert=True)

# --- ДОБАВЛЕНИЕ ТОВАРА (ИСПРАВЛЕНО МОЛЧАНИЕ НА ФОТО) ---

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
        await message.answer("Отправьте **фотографию товара** (картинкой или документом):")
        await state.set_state(AdminSG.add_prod_photo)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число.")

# Принимает картинки и в виде фото, и в виде файлов/документов
@dp.message(AdminSG.add_prod_photo, F.photo | F.document)
async def process_prod_photo(message: types.Message, state: FSMContext):
    photo_id = None
    if message.photo:
        photo_id = message.photo[-1].file_id
    elif message.document and message.document.mime_type.startswith('image/'):
        photo_id = message.document.file_id

    if not photo_id:
        await message.answer("Пожалуйста, отправьте именно изображение.")
        return

    data = await state.get_data()
    add_product_to_db(data['category_id'], data['name'], data['description'], data['price'], photo_id)
    
    await message.answer(
        f"✅ Товар **{data['name']}** успешно добавлен в базу и появится в категории!", 
        reply_markup=get_main_menu(message.from_user.id),
        parse_mode="Markdown"
    )
    await state.clear()

# Обработчики для остальных кнопок админки
@dp.callback_query(F.data.startswith("admin_"))
async def handle_other_admin_callbacks(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS: return
    await callback.answer("Функция находится в разработке", show_alert=True)

async def main():
    logging.basicConfig(level=logging.INFO)
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
