import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

from database import init_db, get_categories

# ⚠️ Убедитесь, что тут вставлен ваш токен
BOT_TOKEN = "8270785657:AAGSAhrPTkWnUQpkSd3SXA8E48BamvfxxIc"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Главное меню
def main_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Каталог"), KeyboardButton(text="Профиль")],
            [KeyboardButton(text="Корзина"), KeyboardButton(text="💬 Отзывы")],
            [KeyboardButton(text="📦 Доступные заказы"), KeyboardButton(text="🚚 Взятые заказы")],
            [KeyboardButton(text="🗄 История заказов")],
            [KeyboardButton(text="🔧 Админка")]
        ],
        resize_keyboard=True
    )
    return keyboard

# Инлайн-кнопки категорий
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

# --- ОБРАБОТЧИКИ ВСЕХ КНОПЕК ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Привет! Выбери нужный раздел меню:", reply_markup=main_menu())

@dp.message(F.text == "Каталог")
async def show_catalog(message: types.Message):
    await message.answer("Выберите категорию:", reply_markup=categories_menu())

@dp.message(F.text == "Профиль")
async def show_profile(message: types.Message):
    text = (
        f"👤 **Профиль:** {message.from_user.username or message.from_user.first_name}\n"
        f"🆔 **ID:** {message.from_user.id}\n"
        f"⭐ **Рейтинг:** 5.0\n"
        f"💰 **Баланс:** 0₽\n"
        f"📦 **Всего заказов:** 0"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "Корзина")
async def show_cart(message: types.Message):
    await message.answer("Корзина пуста.")

@dp.message(F.text.contains("Отзывы"))
async def show_reviews(message: types.Message):
    await message.answer("💬 Отзывов пока нет.")

@dp.message(F.text.contains("Доступные заказы"))
async def show_available_orders(message: types.Message):
    await message.answer("📦 Нет доступных заказов.")

@dp.message(F.text.contains("Взятые заказы"))
async def show_taken_orders(message: types.Message):
    await message.answer("🚚 У вас нет взятых заказов.")

@dp.message(F.text.contains("История заказов"))
async def show_history(message: types.Message):
    await message.answer("🗄 История заказов пуста.")

@dp.message(F.text.contains("Админка"))
async def show_admin(message: types.Message):
    await message.answer("🔧 Панель администратора в разработке.")

# Нажатие на категорию
@dp.callback_query(F.data.startswith("cat_"))
async def process_category(callback: types.CallbackQuery):
    cat_id = callback.data.split("_")[1]
    await callback.message.edit_text(f"Вы выбрали категорию #{cat_id}.")
    await callback.answer()

async def main():
    logging.basicConfig(level=logging.INFO)
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())