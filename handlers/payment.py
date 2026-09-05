# handlers/payment.py
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database import db
from datetime import datetime, timedelta
from utils.platega import platega
import logging

router = Router()
user_payment = {}
user_transactions = {}
user_payment_messages = {}

logger = logging.getLogger(__name__)

# Новый ID для эмодзи Premium в описании тарифа
PREMIUM_EMOJI_ID = "5258185631355378853"

PLANS = {
    "premium": {
        "name": "Premium",
        "devices": "Безлимит",
        "devices_text": "Безлимит",
        "emoji_id": PREMIUM_EMOJI_ID,
        "fallback": "⭐",
        "days_month": 30,
        "days_3months": 90,
        "days_6months": 180,
        "description": "Безлимит устройств\nБезлимит трафика\nНет обязательной подписки на спонсоров"
    }
}

def emoji(emoji_id: str, fallback: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

def get_plan_prices(plan_key: str) -> dict:
    return {
        "month": db.get_price(plan_key, "month"),
        "3months": db.get_price(plan_key, "3months"),
        "6months": db.get_price(plan_key, "6months")
    }

@router.callback_query(F.data == "pay_subscription")
async def pay_subscription(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    
    if user_id in user_payment:
        del user_payment[user_id]
    
    premium_prices = get_plan_prices("premium")
    
    premium_emoji = emoji(PREMIUM_EMOJI_ID, "⭐")
    
    text = (
        f"<b>{premium_emoji} Тариф: Premium</b>\n"
        f"├ Безлимит устройств\n"
        f"├ Безлимит трафика\n"
        f"╰ Нет обязательной подписки на спонсоров\n\n"
        f"{emoji('5323761960829862762', '⚡')} <b>Выберите срок:</b>"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=f"1 мес. — {premium_prices['month']}₽",
            callback_data=f"duration_premium_month"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=f"3 мес. — {premium_prices['3months']}₽",
            callback_data=f"duration_premium_3months"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=f"6 мес. — {premium_prices['6months']}₽",
            callback_data=f"duration_premium_6months"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="« Назад",
            callback_data="back_to_menu"
        )
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("duration_"))
async def select_duration(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    parts = callback.data.split("_")
    plan_key = parts[1]
    duration_key = parts[2]
    
    plan = PLANS[plan_key]
    prices = get_plan_prices(plan_key)
    
    duration_labels = {
        "month": "1 мес.",
        "3months": "3 мес.",
        "6months": "6 мес."
    }
    
    duration_days = {
        "month": plan["days_month"],
        "3months": plan["days_3months"],
        "6months": plan["days_6months"]
    }
    
    label = duration_labels.get(duration_key, "1 мес.")
    price = prices.get(duration_key, 199)
    days = duration_days.get(duration_key, 30)
    
    user_payment[user_id] = {
        "plan": plan_key,
        "duration": duration_key,
        "duration_label": label,
        "price": price,
        "days": days
    }
    
    # СРАЗУ СОЗДАЁМ ПЛАТЁЖНУЮ ССЫЛКУ (БЕЗ ВЫБОРА МЕТОДА ОПЛАТЫ)
    await create_payment_and_show(callback.message, user_id, plan_key, duration_key)
    await callback.answer()

async def create_payment_and_show(message, user_id: int, plan_key: str, duration_key: str):
    if user_id not in user_payment:
        await message.answer("Ошибка, попробуйте сначала")
        return
    
    plan = PLANS[plan_key]
    prices = get_plan_prices(plan_key)
    price = prices.get(duration_key, 199)
    
    duration_names = {
        "month": "1 месяц",
        "3months": "3 месяца",
        "6months": "6 месяцев"
    }
    
    description = f"Оплата Premium на {duration_names.get(duration_key, duration_key)}"
    payload = f"{user_id}:{plan_key}:{duration_key}"
    return_url = f"https://t.me/auranetvpnbot"
    failed_url = f"https://t.me/auranetvpnbot"
    
    user = db.get_user(user_id)
    username = user.get("username") if user else None
    
    # СОЗДАЁМ ПЛАТЁЖ БЕЗ paymentMethod
    transaction = await platega.create_transaction(
        user_id=user_id,
        amount=price,
        description=description,
        return_url=return_url,
        failed_url=failed_url,
        payload=payload,
        username=username
    )
    
    if not transaction:
        await message.answer(
            "❌ Ошибка создания платежа. Попробуйте позже..."
        )
        return
    
    user_transactions[user_id] = transaction.get("transactionId")
    redirect_url = transaction.get("url")
    
    await show_payment_confirmation(
        message,
        user_id,
        plan_key,
        duration_key,
        redirect_url
    )

async def show_payment_confirmation(message, user_id: int, plan_key: str, duration_key: str, redirect_url: str = None):
    plan = PLANS[plan_key]
    prices = get_plan_prices(plan_key)
    
    duration_labels = {
        "month": "1 мес.",
        "3months": "3 мес.",
        "6months": "6 мес."
    }
    
    label = duration_labels.get(duration_key, "1 мес.")
    price = prices.get(duration_key, 199)
    
    privacy_url = "https://telegra.ph/Politika-konfidencialnosti-04-01-26"
    terms_url = "https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19"
    
    agreement_shown = db.get_agreement_shown(user_id)
    
    if not agreement_shown:
        db.set_agreement_shown(user_id)
        text = (
            f"{emoji('5444860552310457690', '💸')} <b>Стоимость:</b> <code>{price} ₽</code>\n"
            f"{emoji('5258258882022612173', '🕛')} <b>Срок:</b> <code>{label}</code>\n\n"
            f"<i>Нажимая «Оплатить» вы подтверждаете что ознакомились с "
            f'<a href="{privacy_url}">политикой конфиденциальности</a> и '
            f'<a href="{terms_url}">пользовательским соглашением</a>.</i>\n\n'
            f"{emoji('5323761960829862762', '⚡')} <b>Нажмите «Оплатить» для перехода к оплате.</b>"
        )
    else:
        text = (
            f"{emoji('5444860552310457690', '💸')} <b>Стоимость:</b> <code>{price} ₽</code>\n"
            f"{emoji('5258258882022612173', '🕛')} <b>Срок:</b> <code>{label}</code>\n\n"
            f"{emoji('5323761960829862762', '⚡')} <b>Нажмите «Оплатить» для перехода к оплате.</b>"
        )
    
    builder = InlineKeyboardBuilder()
    
    if redirect_url:
        builder.row(
            InlineKeyboardButton(
                text="Оплатить",
                url=redirect_url
            )
        )
    
    builder.row(
        InlineKeyboardButton(
            text="Отмена",
            callback_data="pay_cancel"
        )
    )
    
    sent_message = await message.edit_text(
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    
    user_payment_messages[user_id] = sent_message.message_id

@router.callback_query(F.data == "pay_cancel")
async def cancel_payment(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    if user_id in user_payment_messages:
        user_payment_messages.pop(user_id, None)
    
    user_payment.pop(user_id, None)
    user_transactions.pop(user_id, None)
    
    await pay_subscription(callback)