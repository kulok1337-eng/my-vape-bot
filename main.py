import asyncio
import functools
import logging
import os
from html import escape

from aiogram import Bot, Dispatcher, F, types, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton,
)

import database as db

# ---------------- НАСТРОЙКИ ----------------
# Токен задаётся переменной окружения BOT_TOKEN (в панели Bothost -> Переменные),
# в коде и на GitHub его хранить нельзя.
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMINS = [int(x) for x in os.getenv("ADMINS", "1979046241,8079727075").split(",") if x.strip()]
# Чат/канал/группа, куда падают новые заказы с кнопками «Взять заказ / Отменить».
# Бот должен быть там администратором. Если не задан — уведомления идут админам и курьерам в личку.
COURIER_CHAT_ID = int(os.getenv("COURIER_CHAT_ID", "0"))

if not BOT_TOKEN:
    raise SystemExit("Не задана переменная окружения BOT_TOKEN")

TECH_WORKS = False

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

STATUS_EMOJI = {"new": "🆕", "in_progress": "🚚", "completed": "✅", "cancelled": "❌"}


# ---------------- FSM ----------------
class AdminSG(StatesGroup):
    add_cat_name = State()
    rename_cat_name = State()
    prod_name = State()
    prod_price = State()
    prod_desc = State()
    prod_photo = State()
    prod_variants = State()
    edit_price = State()
    edit_variants = State()
    balance_id = State()
    balance_amount = State()
    courier_add = State()
    courier_del = State()
    search = State()
    broadcast = State()


class ReviewSG(StatesGroup):
    comment = State()


# ---------------- ХЕЛПЕРЫ ----------------
def is_admin(uid):
    return uid in ADMINS


def is_courier(uid):
    u = db.get_user(uid)
    return bool(u and u["is_courier"])


def money(x):
    x = float(x or 0)
    return str(int(x)) if x == int(x) else f"{x:.2f}"


def ikb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


def btn(text, data):
    return InlineKeyboardButton(text=text, callback_data=data)


def back_btn(data):
    return [btn("🔙 Назад", data)]


def main_menu(uid):
    rows = [
        [KeyboardButton(text="Каталог"), KeyboardButton(text="Профиль")],
        [KeyboardButton(text="Корзина"), KeyboardButton(text="💬 Отзывы")],
    ]
    if is_admin(uid) or is_courier(uid):
        rows.append([KeyboardButton(text="📦 Доступные заказы"), KeyboardButton(text="🚚 Взятые заказы")])
        rows.append([KeyboardButton(text="🗄 История заказов")])
    if is_admin(uid):
        rows.append([KeyboardButton(text="🔧 Админка")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def user_mention(username, uid):
    return f"@{escape(username)}" if username else f"<code>{uid}</code>"


# ---------------- ТЕХРАБОТЫ ----------------
class TechWorks(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if TECH_WORKS and user and not is_admin(user.id):
            if isinstance(event, types.CallbackQuery):
                await event.answer("⚠️ В боте ведутся технические работы.", show_alert=True)
            else:
                await event.answer("⚠️ В боте ведутся технические работы. Попробуйте зайти позже.")
            return
        return await handler(event, data)


class EnsureUser(BaseMiddleware):
    """Регистрирует пользователя при любом действии (если базу пересоздали или /start не нажимали)."""
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user and not user.is_bot:
            row = db.get_user(user.id)
            if not row or not row["ref_code"]:
                db.register_user(user.id, user.username or user.first_name)
        return await handler(event, data)


dp.message.outer_middleware(TechWorks())
dp.callback_query.outer_middleware(TechWorks())
dp.message.outer_middleware(EnsureUser())
dp.callback_query.outer_middleware(EnsureUser())


@dp.error()
async def on_error(event: types.ErrorEvent):
    logging.exception("Ошибка в обработчике: %s", event.exception)
    cbq = event.update.callback_query
    try:
        if cbq:
            await cbq.answer("⚠️ Произошла ошибка. Попробуйте ещё раз или нажмите /start", show_alert=True)
        elif event.update.message:
            await event.update.message.answer("⚠️ Произошла ошибка. Нажмите /start")
    except Exception:
        pass
    return True


# ---------------- /start ----------------
@dp.message(Command("start"))
async def cmd_start(message: types.Message, command: CommandObject, state: FSMContext):
    await state.clear()
    ref_code = None
    if command.args and command.args.startswith("ref_"):
        ref_code = command.args[4:]
    username = message.from_user.username or message.from_user.first_name
    db.register_user(message.from_user.id, username, ref_code)
    name = escape(message.from_user.first_name or username)
    await message.answer(f"Привет, {name}! 👋\n\nВыберите действие в меню:",
                         reply_markup=main_menu(message.from_user.id))


# ---------------- КАТАЛОГ ----------------
def categories_kb():
    rows, row = [], []
    for c in db.get_categories():
        row.append(btn(c["name"], f"cat_{c['id']}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return ikb(rows)


@dp.message(F.text == "Каталог")
async def show_catalog(message: types.Message):
    await message.answer("Выберите категорию:", reply_markup=categories_kb())


@dp.callback_query(F.data == "back_cats")
async def back_to_cats(cb: types.CallbackQuery):
    await cb.message.delete()
    await cb.message.answer("Выберите категорию:", reply_markup=categories_kb())
    await cb.answer()


@dp.callback_query(F.data.startswith("cat_"))
async def open_category(cb: types.CallbackQuery):
    cat_id = int(cb.data.split("_")[1])
    products = db.get_products(cat_id)
    if not products:
        await cb.answer("В этой категории пока нет товаров", show_alert=True)
        return
    rows, row = [], []
    for p in products:
        row.append(btn(p["name"], f"prod_{p['id']}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(back_btn("back_cats"))
    await cb.message.edit_text("Выберите товар:", reply_markup=ikb(rows))
    await cb.answer()


def product_text(p, variants):
    lines = [f"<b>{escape(p['name'])}</b>", f"💰 {money(p['price'])} руб."]
    if p["description"]:
        lines.append("")
        lines.append(escape(p["description"]))
    lines.append("")
    lines.append("Наличие:")
    for v in variants:
        lines.append(f"{escape(v['name'])} {'✅' if v['stock'] > 0 else '❌'}")
    lines.append("")
    lines.append("Выберите вариант:")
    return "\n".join(lines)


def product_kb(p, variants):
    rows = [[btn(f"{v['name']} ({v['stock']} шт.)", f"var_{v['id']}")] for v in variants if v["stock"] > 0]
    rows.append(back_btn(f"backprod_{p['category_id']}"))
    return ikb(rows)


@dp.callback_query(F.data.startswith("backprod_"))
async def back_to_products(cb: types.CallbackQuery):
    cat_id = int(cb.data.split("_")[1])
    products = db.get_products(cat_id)
    rows, row = [], []
    for p in products:
        row.append(btn(p["name"], f"prod_{p['id']}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(back_btn("back_cats"))
    await cb.message.delete()
    await cb.message.answer("Выберите товар:", reply_markup=ikb(rows))
    await cb.answer()


@dp.callback_query(F.data.startswith("prod_"))
async def open_product(cb: types.CallbackQuery):
    p = db.get_product(int(cb.data.split("_")[1]))
    if not p:
        await cb.answer("Товар не найден", show_alert=True)
        return
    variants = db.get_variants(p["id"])
    text, kb = product_text(p, variants), product_kb(p, variants)
    await cb.message.delete()
    if p["photo_id"]:
        # подпись к фото ограничена 1024 символами
        if len(text) <= 1024:
            await cb.message.answer_photo(p["photo_id"], caption=text, reply_markup=kb)
        else:
            await cb.message.answer_photo(p["photo_id"])
            await cb.message.answer(text, reply_markup=kb)
    else:
        await cb.message.answer(text, reply_markup=kb)
    await cb.answer()


@dp.callback_query(F.data.startswith("var_"))
async def add_variant(cb: types.CallbackQuery):
    vid = int(cb.data.split("_")[1])
    v = db.get_variant(vid)
    if not v:
        await cb.answer("Вариант не найден", show_alert=True)
        return
    ok, msg = db.add_to_cart(cb.from_user.id, v["product_id"], vid)
    await cb.answer(msg, show_alert=True)


# ---------------- КОРЗИНА ----------------
def cart_view(uid):
    items = db.get_cart(uid)
    if not items:
        return "Корзина пуста.", None
    lines = ["🛒 <b>Корзина:</b>", ""]
    total = 0
    rows = []
    for it in items:
        s = it["price"] * it["count"]
        total += s
        title = f"{it['pname']} ({it['vname']})"
        lines.append(f"🔹 {escape(title)} x {it['count']} = {money(s)} р.")
        rows.append([btn(f"❌ {title}", f"cartrm_{it['cart_id']}")])
    percent, dtype = db.get_discount(uid)
    if percent:
        disc = round(total * percent / 100)
        lines.append("")
        lines.append(f"🎁 Реферальная скидка {percent}%: −{money(disc)} р.")
        total -= disc
    lines.append("")
    lines.append(f"<b>Подытог: {money(total)} р.</b> (без доставки)")
    rows.append([btn("✅ Оформить заказ", "checkout")])
    rows.append([btn("🗑 Очистить всё", "cart_clear")])
    return "\n".join(lines), ikb(rows)


@dp.message(F.text == "Корзина")
async def show_cart(message: types.Message):
    text, kb = cart_view(message.from_user.id)
    await message.answer(text, reply_markup=kb)


@dp.callback_query(F.data.startswith("cartrm_"))
async def cart_remove(cb: types.CallbackQuery):
    db.remove_cart_item(int(cb.data.split("_")[1]), cb.from_user.id)
    text, kb = cart_view(cb.from_user.id)
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


@dp.callback_query(F.data == "cart_clear")
async def cart_clear(cb: types.CallbackQuery):
    db.clear_cart(cb.from_user.id)
    await cb.message.edit_text("Корзина пуста.")
    await cb.answer()


# ---------------- ОФОРМЛЕНИЕ ----------------
def delivery_kb():
    rows = [
        [btn(f"{db.DELIVERY['pickup'][0]} ({money(db.DELIVERY['pickup'][1])}₽)", "dlv_pickup")],
        [btn(f"{db.DELIVERY['norilsk'][0]} (+{money(db.DELIVERY['norilsk'][1])}₽)", "dlv_norilsk")],
        [btn(f"🚚 Доставка: Талнах (+{money(db.DELIVERY['talnah_bus'][1])}₽)", "dlv_talnah")],
        back_btn("dlv_back"),
    ]
    return ikb(rows)


@dp.callback_query(F.data == "checkout")
async def checkout(cb: types.CallbackQuery):
    if not db.get_cart(cb.from_user.id):
        await cb.message.edit_text("Корзина пуста.")
        return await cb.answer()
    await cb.message.edit_text("📍 <b>Выберите способ получения:</b>", reply_markup=delivery_kb())
    await cb.answer()


@dp.callback_query(F.data == "dlv_back")
async def delivery_back(cb: types.CallbackQuery):
    text, kb = cart_view(cb.from_user.id)
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


@dp.callback_query(F.data == "dlv_talnah")
async def delivery_talnah(cb: types.CallbackQuery):
    price = db.DELIVERY["talnah_bus"][1]
    await cb.message.edit_text(
        "🚌 <b>Доставка в Талнах:</b>",
        reply_markup=ikb([[btn(f"🚌 До автовокзала (+{money(price)}₽)", "dlv_talnah_bus")], back_btn("checkout")]))
    await cb.answer()


def order_card(o, title=None):
    head = title or f"{STATUS_EMOJI.get(o['status'], '')} <b>Заказ #{o['id']}</b>"
    return (
        f"{head}\n"
        f"👤 User: {user_mention(o['username'], o['user_id'])} (ID: <code>{o['user_id']}</code>)\n"
        f"📍 {escape(o['delivery_label'] or '')}\n"
        f"📦 {escape(o['items_text'] or '')}\n"
        f"💰 Итого: {money(o['total_price'])} р."
    )


def new_order_kb(oid):
    return ikb([[btn("🏃 Взять заказ", f"take_{oid}")], [btn("❌ Отменить", f"cancel_{oid}")]])


async def notify_staff(o):
    text = order_card(o, f"🆕 <b>Заказ #{o['id']}</b>")
    kb = new_order_kb(o["id"])
    if COURIER_CHAT_ID:
        try:
            m = await bot.send_message(COURIER_CHAT_ID, text, reply_markup=kb)
            db.set_order_notify(o["id"], m.chat.id, m.message_id)
            return
        except Exception as e:
            logging.warning("Не удалось отправить заказ в чат курьеров: %s", e)
    for uid in set(ADMINS + db.get_courier_ids()):
        try:
            await bot.send_message(uid, text, reply_markup=kb)
        except Exception:
            pass


@dp.callback_query(F.data.startswith("dlv_"))
async def make_order(cb: types.CallbackQuery):
    key = cb.data[4:]
    if key not in db.DELIVERY:
        return await cb.answer()
    username = cb.from_user.username or cb.from_user.first_name
    oid, err = db.create_order(cb.from_user.id, username, key)
    if err:
        await cb.message.edit_text(f"⚠️ {err}")
        return await cb.answer()
    o = db.get_order(oid)
    lines = [
        f"✅ <b>Заказ #{oid} создан!</b>", "",
        f"📦 Тип: {escape(o['delivery_label'])}",
        f"🛍 Товары: {money(o['goods_total'])}₽",
    ]
    if o["discount"]:
        lines.append(f"🎁 Скидка: −{money(o['discount'])}₽")
    if o["delivery_price"]:
        lines.append(f"🚚 Доставка: {money(o['delivery_price'])}₽")
    if o["balance_used"]:
        lines.append(f"💳 Списано с баланса: {money(o['balance_used'])}₽")
    lines.append(f"💰 <b>Итого: {money(o['total_price'])}₽</b>")
    lines.append("")
    lines.append("Ожидайте, курьер свяжется с вами.")
    await cb.message.edit_text("\n".join(lines))
    await notify_staff(o)
    await cb.answer()


# ---------------- ЗАКАЗЫ КУРЬЕРА ----------------
def staff_only(uid):
    return is_admin(uid) or is_courier(uid)


@dp.message(F.text == "📦 Доступные заказы")
async def available_orders(message: types.Message):
    if not staff_only(message.from_user.id):
        return await message.answer("⛔ У вас нет доступа к этому разделу.")
    orders = db.get_orders_by_status("new")
    if not orders:
        return await message.answer("📦 Новых заказов нет.")
    for o in orders:
        await message.answer(order_card(o, f"🆕 <b>Заказ #{o['id']}</b>"), reply_markup=new_order_kb(o["id"]))


@dp.message(F.text == "🚚 Взятые заказы")
async def taken_orders(message: types.Message):
    if not staff_only(message.from_user.id):
        return await message.answer("⛔ У вас нет доступа к этому разделу.")
    orders = db.get_courier_orders(message.from_user.id)
    if not orders:
        return await message.answer("🚚 У вас нет активных заказов.")
    for o in orders:
        await message.answer(order_card(o, f"🚚 <b>Заказ в работе #{o['id']}</b>"),
                             reply_markup=ikb([[btn("✅ Выдан", f"done_{o['id']}")],
                                               [btn("❌ Отменить", f"cancel_{o['id']}")]]))


@dp.message(F.text == "🗄 История заказов")
async def orders_history(message: types.Message):
    if not staff_only(message.from_user.id):
        return await message.answer("⛔ У вас нет доступа к этому разделу.")
    orders = db.get_orders_by_status("completed", 15)
    if not orders:
        return await message.answer("🗄 История пуста.")
    text = "🗄 <b>Выданные заказы:</b>\n\n" + "\n".join(
        f"✅ #{o['id']} | {user_mention(o['username'], o['user_id'])} | {money(o['total_price'])} р. | {escape(o['delivery_label'] or '')}"
        for o in orders)
    await message.answer(text)


@dp.callback_query(F.data.startswith("take_"))
async def take_order(cb: types.CallbackQuery):
    if not staff_only(cb.from_user.id):
        return await cb.answer("Нет доступа", show_alert=True)
    oid = int(cb.data.split("_")[1])
    if not db.take_order(oid, cb.from_user.id):
        return await cb.answer("Заказ уже взят или отменён", show_alert=True)
    name = f"@{cb.from_user.username}" if cb.from_user.username else cb.from_user.full_name
    await cb.message.edit_text(f"🔒 Заказ #{oid} взят курьером {escape(name)}.")
    o = db.get_order(oid)
    try:
        await bot.send_message(o["user_id"], f"🚚 Курьер взял ваш заказ #{oid} в работу.")
    except Exception:
        pass
    try:
        await bot.send_message(cb.from_user.id, order_card(o, f"🚚 <b>Заказ в работе #{oid}</b>"),
                               reply_markup=ikb([[btn("✅ Выдан", f"done_{oid}")], [btn("❌ Отменить", f"cancel_{oid}")]]))
    except Exception:
        pass
    await cb.answer()


@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_menu(cb: types.CallbackQuery):
    oid = int(cb.data.split("_")[1])
    o = db.get_order(oid)
    if not o or o["status"] in ("completed", "cancelled"):
        return await cb.answer("Заказ уже закрыт", show_alert=True)
    if not (staff_only(cb.from_user.id) or cb.from_user.id == o["user_id"]):
        return await cb.answer("Нет доступа", show_alert=True)
    await cb.message.edit_text(
        order_card(o),
        reply_markup=ikb([
            [btn("💸 Отмена с возвратом (на баланс)", f"cnc_ref_{oid}")],
            [btn("🚫 Отмена без возврата", f"cnc_no_{oid}")],
            back_btn(f"cnc_back_{oid}"),
        ]))
    await cb.answer()


@dp.callback_query(F.data.startswith("cnc_back_"))
async def cancel_back(cb: types.CallbackQuery):
    oid = int(cb.data.split("_")[2])
    o = db.get_order(oid)
    kb = new_order_kb(oid) if o and o["status"] == "new" else ikb(
        [[btn("✅ Выдан", f"done_{oid}")], [btn("❌ Отменить", f"cancel_{oid}")]])
    await cb.message.edit_text(order_card(o), reply_markup=kb)
    await cb.answer()


@dp.callback_query(F.data.startswith("cnc_ref_") | F.data.startswith("cnc_no_"))
async def do_cancel(cb: types.CallbackQuery):
    parts = cb.data.split("_")
    refund = parts[1] == "ref"
    oid = int(parts[2])
    o = db.get_order(oid)
    if not o:
        return await cb.answer()
    if not (staff_only(cb.from_user.id) or cb.from_user.id == o["user_id"]):
        return await cb.answer("Нет доступа", show_alert=True)
    if not db.cancel_order(oid, refund):
        return await cb.answer("Заказ уже закрыт", show_alert=True)
    text = (f"❌ Заказ #{oid} отменён (с возвратом на баланс)." if refund
            else f"❌ Заказ #{oid} отменён без возврата денег.")
    await cb.message.edit_text(text)
    if cb.from_user.id != o["user_id"]:
        try:
            await bot.send_message(o["user_id"], text)
        except Exception:
            pass
    await cb.answer()


@dp.callback_query(F.data.startswith("done_"))
async def done_order(cb: types.CallbackQuery):
    if not staff_only(cb.from_user.id):
        return await cb.answer("Нет доступа", show_alert=True)
    oid = int(cb.data.split("_")[1])
    if not db.complete_order(oid):
        return await cb.answer("Заказ нельзя завершить", show_alert=True)
    o = db.get_order(oid)
    await cb.message.edit_text(f"✅ Заказ #{oid} выдан.")
    stars = [btn(f"⭐ {i}", f"rate_{oid}_{i}") for i in range(1, 6)]
    try:
        await bot.send_message(o["user_id"], f"🎉 <b>Ваш заказ #{oid} выдан!</b>\nОцените обслуживание:",
                               reply_markup=ikb([stars]))
    except Exception:
        pass
    await cb.answer()


# ---------------- ОЦЕНКА / ОТЗЫВЫ ----------------
@dp.callback_query(F.data.startswith("rate_"))
async def rate(cb: types.CallbackQuery, state: FSMContext):
    _, oid, rating = cb.data.split("_")
    oid, rating = int(oid), int(rating)
    o = db.get_order(oid)
    if not o or o["user_id"] != cb.from_user.id or db.order_reviewed(oid):
        return await cb.answer("Отзыв уже оставлен", show_alert=True)
    await state.update_data(order_id=oid, rating=rating, courier_id=o["courier_id"])
    await state.set_state(ReviewSG.comment)
    await cb.message.edit_text(
        f"Спасибо за оценку ({'⭐' * rating})!\n\nНапишите короткий отзыв (или отправьте «-», чтобы пропустить):")
    await cb.answer()


@dp.message(ReviewSG.comment, F.text)
async def review_comment(message: types.Message, state: FSMContext):
    d = await state.get_data()
    comment = "" if message.text.strip() == "-" else message.text.strip()
    db.add_review(d["order_id"], message.from_user.id, d["courier_id"], d["rating"], comment)
    await state.clear()
    await message.answer("❤️ Спасибо за отзыв!", reply_markup=main_menu(message.from_user.id))


def review_view(idx, uid):
    total = db.count_reviews()
    if total == 0:
        return "💬 Пока отзывов нет.", None
    idx %= total
    r = db.get_review_by_index(idx)
    who = f"@{escape(r['username'])}" if r["username"] else "покупателя"
    date = str(r["created_at"])[:10]
    text = f"💬 <b>Отзыв от {who}</b> ({date})\n\n{escape(r['comment']) if r['comment'] else '⭐' * r['rating']}"
    nav = [btn(f"{idx + 1}/{total}", "noop"), btn("➡️", f"rev_{idx + 1}")]
    rows = [nav]
    if is_admin(uid):
        rows.append([btn("🗑 Удалить отзыв", f"revdel_{r['id']}")])
    return text, ikb(rows)


@dp.message(F.text == "💬 Отзывы")
async def show_reviews(message: types.Message):
    text, kb = review_view(0, message.from_user.id)
    await message.answer(text, reply_markup=kb)


@dp.callback_query(F.data.startswith("rev_"))
async def reviews_page(cb: types.CallbackQuery):
    text, kb = review_view(int(cb.data.split("_")[1]), cb.from_user.id)
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


@dp.callback_query(F.data.startswith("revdel_"))
async def review_delete(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer()
    db.delete_review(int(cb.data.split("_")[1]))
    text, kb = review_view(0, cb.from_user.id)
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer("Удалено")


@dp.callback_query(F.data == "noop")
async def noop(cb: types.CallbackQuery):
    await cb.answer()


# ---------------- ПРОФИЛЬ ----------------
def profile_view(uid, fallback_name):
    u = db.get_user(uid)
    name = escape(u["username"] if u and u["username"] else fallback_name)
    text = (
        f"👤 <b>Профиль:</b> {name}\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"⭐ Рейтинг: {u['rating'] if u else 5.0}\n"
        f"💰 Баланс: {money(u['balance'] if u else 0)}₽\n"
        f"📦 Всего заказов: {db.count_user_orders(uid)}"
    )
    kb = ikb([[btn("📦 Мои заказы", "prof_orders")], [btn("🎁 Реферальная система", "prof_ref")]])
    return text, kb


@dp.message(F.text == "Профиль")
async def show_profile(message: types.Message):
    text, kb = profile_view(message.from_user.id, message.from_user.first_name)
    await message.answer(text, reply_markup=kb)


@dp.callback_query(F.data == "prof_back")
async def profile_back(cb: types.CallbackQuery):
    text, kb = profile_view(cb.from_user.id, cb.from_user.first_name)
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


@dp.callback_query(F.data == "prof_orders")
async def my_orders(cb: types.CallbackQuery):
    orders = db.get_user_orders(cb.from_user.id)
    if not orders:
        return await cb.answer("У вас пока нет заказов", show_alert=True)
    parts = ["📦 <b>Ваши заказы:</b>\n"]
    for o in orders:
        parts.append(
            f"<b>#{o['id']}</b> {STATUS_EMOJI.get(o['status'], '')}\n"
            f"📅 {str(o['created_at'])[:10]}\n"
            f"📍 {escape(o['delivery_label'] or '')}\n"
            f"🛒 {escape(o['items_text'] or '')}\n"
            f"💰 <b>{money(o['total_price'])}₽</b>\n"
            "──────────────")
    await cb.message.answer("\n".join(parts)[:4000])
    await cb.answer()


@dp.callback_query(F.data == "prof_ref")
async def ref_system(cb: types.CallbackQuery):
    uid = cb.from_user.id
    u = db.get_user(uid)
    active, pending = db.active_referrals(uid), db.pending_referrals(uid)
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{u['ref_code']}"
    if active >= 10:
        level, left = "🏆 Максимальный уровень: доступна разовая скидка 10%", ""
    elif active >= 5:
        level, left = "🥈 Вечная скидка 5% активна", f"📊 До разовой скидки 10%: еще {10 - active} рефералов"
    else:
        level, left = "Начальный уровень", f"📊 До вечной скидки 5%: еще {5 - active} рефералов"
    text = (
        "🎁 <b>Реферальная система</b>\n\n"
        f"👥 Активных рефералов: {active}\n"
        f"⏳ Ожидают активации: {pending}\n"
        f"{level}\n{left}\n\n"
        f"🔗 <b>Ваша реферальная ссылка:</b>\n<code>{link}</code>\n\n"
        "📋 <b>Как это работает:</b>\n"
        "• Приглашай друзей и получай скидки 💸\n"
        "• 5-9 активных рефералов → вечная скидка 5% на товары\n"
        "• 10+ активных рефералов → разовая скидка 10% на товары\n\n"
        "⚠️ Реферал засчитывается только после:\n"
        "1️⃣ Первого запуска бота\n2️⃣ Оформления заказа\n3️⃣ Получения заказа (статус «выдан»)\n\n"
        "💡 <i>Рефералом может стать только новый пользователь, которого еще нет в базе данных бота.</i>\n\n"
        "⚠️ <i>После использования скидки 10%, количество рефералов сгорает до 5 (остается вечная скидка 5%).</i>\n\n"
        "📦 <i>Скидка применяется только к стоимости товаров (без доставки).</i>"
    )
    await cb.message.edit_text(text, reply_markup=ikb([
        [btn("👥 Мои рефералы", "ref_list")], [btn("ℹ️ Подробная информация", "ref_info")], back_btn("prof_back")]))
    await cb.answer()


@dp.callback_query(F.data == "ref_list")
async def ref_list(cb: types.CallbackQuery):
    rows = db.list_referrals(cb.from_user.id)
    if not rows:
        text = "📋 <b>Список рефералов</b>\n\nУ вас пока нет рефералов.\nПоделитесь своей реферальной ссылкой с друзьями!"
    else:
        names = {"active": "✅ активен", "pending": "⏳ ожидает", "burned": "🔥 сгорел"}
        text = "📋 <b>Список рефералов</b>\n\n" + "\n".join(
            f"• {user_mention(r['username'], r['referred_id'])} — {names.get(r['status'], r['status'])}" for r in rows)
    await cb.message.edit_text(text, reply_markup=ikb([back_btn("prof_ref")]))
    await cb.answer()


@dp.callback_query(F.data == "ref_info")
async def ref_info(cb: types.CallbackQuery):
    await ref_list(cb)


# ---------------- АДМИНКА ----------------
def admin_kb():
    return ikb([
        [btn("📁 Добавить категорию", "ad_addcat"), btn("🗑 Удалить категорию", "ad_delcat")],
        [btn("✏️ Переименовать категорию", "ad_rencat")],
        [btn("📦 Добавить товар", "ad_addprod"), btn("✏️ Редактирование", "ad_edit")],
        [btn("📢 Рассылка", "ad_broadcast"), btn("📊 Статистика", "ad_stats")],
        [btn("📈 Статистика за день", "ad_stats_day")],
        [btn("👤 Назначить курьера", "ad_cour_add"), btn("👤 Разжаловать курьера", "ad_cour_del")],
        [btn("🔎 Поиск / Инфо", "ad_search"), btn("💰 Выдать баланс", "ad_balance")],
        [btn("🔧 Технические работы", "ad_tech")],
    ])


def admin_only(handler):
    """Декоратор: пропускает только админов."""
    @functools.wraps(handler)
    async def wrapper(cb: types.CallbackQuery, *a, **kw):
        if not is_admin(cb.from_user.id):
            return await cb.answer("Нет доступа", show_alert=True)
        return await handler(cb, *a, **kw)
    return wrapper


@dp.message(F.text == "🔧 Админка")
async def admin_panel(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ У вас нет доступа к этому разделу.")
    await state.clear()
    await message.answer("🔧 <b>Панель Степы</b>", reply_markup=admin_kb())


def cats_kb(prefix, extra_back=None):
    rows = [[btn(c["name"], f"{prefix}_{c['id']}")] for c in db.get_categories()]
    if extra_back:
        rows.append(back_btn(extra_back))
    return ikb(rows)


# --- категории
@dp.callback_query(F.data == "ad_addcat")
@admin_only
async def ad_addcat(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("Введите название новой категории:")
    await state.set_state(AdminSG.add_cat_name)
    await cb.answer()


@dp.message(AdminSG.add_cat_name, F.text)
async def ad_addcat_done(message: types.Message, state: FSMContext):
    db.add_category(message.text.strip())
    await message.answer(f"✅ Категория «{escape(message.text)}» создана.")
    await state.clear()


@dp.callback_query(F.data == "ad_rencat")
@admin_only
async def ad_rencat(cb: types.CallbackQuery):
    await cb.message.edit_text("Выберите категорию для переименования:", reply_markup=cats_kb("rencat"))
    await cb.answer()


@dp.callback_query(F.data.startswith("rencat_"))
@admin_only
async def ad_rencat_pick(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(cat_id=int(cb.data.split("_")[1]))
    await state.set_state(AdminSG.rename_cat_name)
    await cb.message.edit_text("Введите новое название категории:")
    await cb.answer()


@dp.message(AdminSG.rename_cat_name, F.text)
async def ad_rencat_done(message: types.Message, state: FSMContext):
    d = await state.get_data()
    db.rename_category(d["cat_id"], message.text.strip())
    await message.answer("✅ Категория переименована.")
    await state.clear()


@dp.callback_query(F.data == "ad_delcat")
@admin_only
async def ad_delcat(cb: types.CallbackQuery):
    await cb.message.edit_text("Выберите категорию для удаления (удалятся и её товары):", reply_markup=cats_kb("delcat"))
    await cb.answer()


@dp.callback_query(F.data.startswith("delcat_"))
@admin_only
async def ad_delcat_do(cb: types.CallbackQuery):
    db.delete_category(int(cb.data.split("_")[1]))
    await cb.message.edit_text("🗑 Категория и её товары удалены.")
    await cb.answer()


# --- добавление товара
def parse_variants(text):
    """Строки вида «Название:кол-во» или просто «Название» (кол-во 1)."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            name, qty = line.rsplit(":", 1)
            try:
                out.append((name.strip(), int(qty.strip())))
                continue
            except ValueError:
                pass
        out.append((line, 1))
    return out


@dp.callback_query(F.data == "ad_addprod")
@admin_only
async def ad_addprod(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("Выберите категорию для нового товара:", reply_markup=cats_kb("apcat"))
    await cb.answer()


@dp.callback_query(F.data.startswith("apcat_"))
@admin_only
async def ad_addprod_cat(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(category_id=int(cb.data.split("_")[1]))
    await state.set_state(AdminSG.prod_name)
    await cb.message.edit_text("Введите название товара:")
    await cb.answer()


@dp.message(AdminSG.prod_name, F.text)
async def ad_prod_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminSG.prod_price)
    await message.answer("Введите цену (числом):")


@dp.message(AdminSG.prod_price, F.text)
async def ad_prod_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", "."))
    except ValueError:
        return await message.answer("Введите корректное число.")
    await state.update_data(price=price)
    await state.set_state(AdminSG.prod_desc)
    await message.answer("Введите описание (или «-», чтобы пропустить):")


@dp.message(AdminSG.prod_desc, F.text)
async def ad_prod_desc(message: types.Message, state: FSMContext):
    await state.update_data(description="" if message.text.strip() == "-" else message.text.strip())
    await state.set_state(AdminSG.prod_photo)
    await message.answer("Отправьте фото товара (или «-», чтобы пропустить):")


@dp.message(AdminSG.prod_photo)
async def ad_prod_photo(message: types.Message, state: FSMContext):
    photo_id = None
    if message.photo:
        photo_id = message.photo[-1].file_id
    elif message.document and (message.document.mime_type or "").startswith("image/"):
        photo_id = message.document.file_id
    elif not (message.text and message.text.strip() == "-"):
        return await message.answer("Отправьте изображение или «-».")
    await state.update_data(photo_id=photo_id)
    await state.set_state(AdminSG.prod_variants)
    await message.answer(
        "Введите варианты (вкусы/цвета) и наличие, каждый с новой строки в формате <code>Название:количество</code>.\n\n"
        "Пример:\n<code>Малина мята:3\nДыня банан:2\nЛимон мята:0</code>")


@dp.message(AdminSG.prod_variants, F.text)
async def ad_prod_variants(message: types.Message, state: FSMContext):
    variants = parse_variants(message.text)
    if not variants:
        return await message.answer("Не удалось разобрать варианты, попробуйте ещё раз.")
    d = await state.get_data()
    db.add_product(d["category_id"], d["name"], d.get("description", ""), d["price"], d.get("photo_id"), variants)
    await message.answer(f"✅ Товар <b>{escape(d['name'])}</b> добавлен ({len(variants)} вар.).",
                         reply_markup=main_menu(message.from_user.id))
    await state.clear()


# --- редактирование
@dp.callback_query(F.data == "ad_edit")
@admin_only
async def ad_edit(cb: types.CallbackQuery):
    await cb.message.edit_text("Выберите категорию:", reply_markup=cats_kb("edcat"))
    await cb.answer()


@dp.callback_query(F.data.startswith("edcat_"))
@admin_only
async def ad_edit_cat(cb: types.CallbackQuery):
    cid = int(cb.data.split("_")[1])
    rows = [[btn(p["name"], f"edprod_{p['id']}")] for p in db.get_products(cid)]
    if not rows:
        return await cb.answer("В категории нет товаров", show_alert=True)
    rows.append(back_btn("ad_edit"))
    await cb.message.edit_text("Выберите товар:", reply_markup=ikb(rows))
    await cb.answer()


@dp.callback_query(F.data.startswith("edprod_"))
@admin_only
async def ad_edit_prod(cb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    p = db.get_product(int(cb.data.split("_")[1]))
    text = product_text(p, db.get_variants(p["id"])).replace("\n\nВыберите вариант:", "")
    await cb.message.edit_text(text, reply_markup=ikb([
        [btn("💰 Изменить цену", f"edprice_{p['id']}")],
        [btn("📦 Изменить наличие", f"edstock_{p['id']}")],
        [btn("🗑 Удалить товар", f"eddel_{p['id']}")],
        back_btn(f"edcat_{p['category_id']}"),
    ]))
    await cb.answer()


@dp.callback_query(F.data.startswith("edprice_"))
@admin_only
async def ad_edit_price(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(product_id=int(cb.data.split("_")[1]))
    await state.set_state(AdminSG.edit_price)
    await cb.message.edit_text("Введите новую цену:")
    await cb.answer()


@dp.message(AdminSG.edit_price, F.text)
async def ad_edit_price_done(message: types.Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", "."))
    except ValueError:
        return await message.answer("Введите число.")
    d = await state.get_data()
    db.update_product_price(d["product_id"], price)
    await message.answer("✅ Цена обновлена.")
    await state.clear()


@dp.callback_query(F.data.startswith("edstock_"))
@admin_only
async def ad_edit_stock(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(product_id=int(cb.data.split("_")[1]))
    await state.set_state(AdminSG.edit_variants)
    await cb.message.edit_text(
        "Введите варианты с новым остатком, по одному в строке: <code>Название:количество</code>.\n"
        "Существующие обновятся, новые добавятся. Для «нет в наличии» укажите 0.")
    await cb.answer()


@dp.message(AdminSG.edit_variants, F.text)
async def ad_edit_stock_done(message: types.Message, state: FSMContext):
    d = await state.get_data()
    db.upsert_variants(d["product_id"], parse_variants(message.text))
    await message.answer("✅ Наличие обновлено.")
    await state.clear()


@dp.callback_query(F.data.startswith("eddel_"))
@admin_only
async def ad_edit_delete(cb: types.CallbackQuery):
    db.delete_product(int(cb.data.split("_")[1]))
    await cb.message.edit_text("🗑 Товар удалён.")
    await cb.answer()


# --- баланс, курьеры, поиск
@dp.callback_query(F.data == "ad_balance")
@admin_only
async def ad_balance(cb: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminSG.balance_id)
    await cb.message.edit_text("Введите Telegram ID или @username пользователя:")
    await cb.answer()


@dp.message(AdminSG.balance_id, F.text)
async def ad_balance_id(message: types.Message, state: FSMContext):
    u = db.find_user(message.text)
    if not u:
        return await message.answer("❌ Пользователь не найден в базе.")
    await state.update_data(target=u["user_id"])
    await state.set_state(AdminSG.balance_amount)
    await message.answer("Введите сумму пополнения (можно отрицательную для списания):")


@dp.message(AdminSG.balance_amount, F.text)
async def ad_balance_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        return await message.answer("Введите число.")
    d = await state.get_data()
    db.update_balance(d["target"], amount)
    await message.answer(f"✅ Баланс <code>{d['target']}</code> изменён на {money(amount)} руб.")
    try:
        await bot.send_message(d["target"], f"💰 Ваш баланс изменён на {money(amount)}₽.")
    except Exception:
        pass
    await state.clear()


@dp.callback_query(F.data == "ad_cour_add")
@admin_only
async def ad_cour_add(cb: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminSG.courier_add)
    await cb.message.edit_text("Введите ID или @username нового курьера (он должен хотя бы раз запустить бота):")
    await cb.answer()


@dp.message(AdminSG.courier_add, F.text)
async def ad_cour_add_done(message: types.Message, state: FSMContext):
    u = db.find_user(message.text)
    if not u:
        return await message.answer("❌ Пользователь не найден в базе.")
    db.set_courier(u["user_id"], 1)
    await message.answer(f"✅ <code>{u['user_id']}</code> назначен курьером.")
    try:
        await bot.send_message(u["user_id"], "🚚 Вас назначили курьером. Нажмите /start, чтобы обновить меню.")
    except Exception:
        pass
    await state.clear()


@dp.callback_query(F.data == "ad_cour_del")
@admin_only
async def ad_cour_del(cb: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminSG.courier_del)
    await cb.message.edit_text("Введите ID или @username курьера для снятия прав:")
    await cb.answer()


@dp.message(AdminSG.courier_del, F.text)
async def ad_cour_del_done(message: types.Message, state: FSMContext):
    u = db.find_user(message.text)
    if not u:
        return await message.answer("❌ Пользователь не найден в базе.")
    db.set_courier(u["user_id"], 0)
    await message.answer(f"✅ Права курьера у <code>{u['user_id']}</code> сняты.")
    await state.clear()


@dp.callback_query(F.data == "ad_search")
@admin_only
async def ad_search(cb: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminSG.search)
    await cb.message.edit_text("Введите ID или @username пользователя:")
    await cb.answer()


@dp.message(AdminSG.search, F.text)
async def ad_search_done(message: types.Message, state: FSMContext):
    u = db.find_user(message.text)
    if not u:
        await message.answer("❌ Пользователь не найден в базе.")
    else:
        await message.answer(
            "🔎 <b>Информация о пользователе:</b>\n\n"
            f"👤 Username: {user_mention(u['username'], u['user_id'])}\n"
            f"🆔 ID: <code>{u['user_id']}</code>\n"
            f"💰 Баланс: {money(u['balance'])} руб.\n"
            f"⭐ Рейтинг: {u['rating']}\n"
            f"🚚 Курьер: {'Да' if u['is_courier'] else 'Нет'}\n"
            f"👥 Активных рефералов: {db.active_referrals(u['user_id'])}\n"
            f"📦 Заказов: {db.count_user_orders(u['user_id'])}")
    await state.clear()


# --- статистика, рассылка, техработы
@dp.callback_query(F.data == "ad_stats")
@admin_only
async def ad_stats(cb: types.CallbackQuery):
    n, s, users, new = db.get_stats(False)
    await cb.message.edit_text(
        "📊 <b>Общая статистика:</b>\n\n"
        f"👥 Пользователей: <b>{users}</b>\n📦 Выдано заказов: <b>{n}</b>\n"
        f"🆕 Новых заказов: <b>{new}</b>\n💰 Выручка: <b>{money(s)} руб.</b>")
    await cb.answer()


@dp.callback_query(F.data == "ad_stats_day")
@admin_only
async def ad_stats_day(cb: types.CallbackQuery):
    n, s, _, _ = db.get_stats(True)
    await cb.message.edit_text(
        f"📈 <b>Статистика за сегодня:</b>\n\n📦 Заказов: <b>{n}</b>\n💰 Выручка: <b>{money(s)} руб.</b>")
    await cb.answer()


@dp.callback_query(F.data == "ad_broadcast")
@admin_only
async def ad_broadcast(cb: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminSG.broadcast)
    await cb.message.edit_text("Отправьте сообщение (текст или фото с подписью) для рассылки всем пользователям:")
    await cb.answer()


@dp.message(AdminSG.broadcast)
async def ad_broadcast_do(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🚀 Рассылка запущена...")
    sent = failed = 0
    for uid in db.get_all_user_ids():
        try:
            await message.copy_to(uid)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await message.answer(f"✅ Рассылка завершена.\nУспешно: {sent}\nОшибок: {failed}")


@dp.callback_query(F.data == "ad_tech")
@admin_only
async def ad_tech(cb: types.CallbackQuery):
    global TECH_WORKS
    TECH_WORKS = not TECH_WORKS
    await cb.message.edit_text(f"🔧 Технические работы: <b>{'ВКЛЮЧЕНЫ ⛔' if TECH_WORKS else 'ВЫКЛЮЧЕНЫ ✅'}</b>")
    await cb.answer()


async def main():
    logging.basicConfig(level=logging.INFO)
    db.init_db()
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
