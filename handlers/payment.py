# handlers/payment.py
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database import db
from utils.platega import platega, PLATEGA_METHOD_SBP, PLATEGA_METHOD_CARD
from utils.cryptobot import cryptobot
import logging

router = Router()
user_payment = {}
user_transactions = {}
user_payment_messages = {}

logger = logging.getLogger(__name__)

# Премиум-эмодзи
PREMIUM_EMOJI_ID = "5258185631355378853"

EMOJI_MONEY = "5444860552310457690"      # 💰
EMOJI_CLOCK = "5258258882022612173"      # ⏱️
EMOJI_SBP = "5425008221330880308"        # 💸
EMOJI_CARD = "5280695018082804074"       # 💳
EMOJI_CRYPTO = "5361914370068613491"     # 💲
EMOJI_BOLT = "5323761960829862762"       # ⚡

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
        f"{emoji(EMOJI_BOLT, '⚡')} <b>Выберите срок:</b>"
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=f"1 мес. — {premium_prices['month']}₽",
            callback_data="duration_premium_month"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=f"3 мес. — {premium_prices['3months']}₽",
            callback_data="duration_premium_3months"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=f"6 мес. — {premium_prices['6months']}₽",
            callback_data="duration_premium_6months"
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
        "month": "1 месяц",
        "3months": "3 месяца",
        "6months": "6 месяцев"
    }

    duration_days = {
        "month": plan["days_month"],
        "3months": plan["days_3months"],
        "6months": plan["days_6months"]
    }

    label = duration_labels.get(duration_key, "1 месяц")
    price = prices.get(duration_key, 199)
    days = duration_days.get(duration_key, 30)

    user_payment[user_id] = {
        "plan": plan_key,
        "duration": duration_key,
        "duration_label": label,
        "price": price,
        "days": days
    }

    await show_payment_methods(callback.message, user_id)


async def show_payment_methods(message, user_id: int):
    """Экран выбора способа оплаты."""
    if user_id not in user_payment:
        await message.answer("Ошибка, попробуйте сначала")
        return

    data = user_payment[user_id]
    price = data["price"]
    label = data["duration_label"]

    text = (
        f"{emoji(EMOJI_MONEY, '💰')} <b>Стоимость:</b> <code>{price} ₽</code>\n"
        f"{emoji(EMOJI_CLOCK, '⏱️')} <b>Срок:</b> <code>{label}</code>\n\n"
        f"{emoji(EMOJI_BOLT, '⚡')} <b>Выберите способ оплаты:</b>"
    )

    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="СБП",
            callback_data="pay_method_sbp",
            icon_custom_emoji_id=EMOJI_SBP
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Банковская карта",
            callback_data="pay_method_card",
            icon_custom_emoji_id=EMOJI_CARD
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="CryptoBot",
            callback_data="pay_method_crypto",
            icon_custom_emoji_id=EMOJI_CRYPTO
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="« Назад",
            callback_data="pay_subscription"
        )
    )

    sent_message = await message.edit_text(
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

    user_payment_messages[user_id] = sent_message.message_id


# ==================== СБП ====================

@router.callback_query(F.data == "pay_method_sbp")
async def pay_method_sbp(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    if user_id not in user_payment:
        await callback.message.edit_text("Сессия истекла, начните заново.")
        return

    logger.info(f"User {user_id} selected payment method: СБП (2)")
    await create_platega_payment(callback.message, user_id, PLATEGA_METHOD_SBP)


# ==================== Банковская карта ====================

@router.callback_query(F.data == "pay_method_card")
async def pay_method_card(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    if user_id not in user_payment:
        await callback.message.edit_text("Сессия истекла, начните заново.")
        return

    logger.info(f"User {user_id} selected payment method: Карта (11)")
    await create_platega_payment(callback.message, user_id, PLATEGA_METHOD_CARD)


# ==================== CryptoBot ====================

@router.callback_query(F.data == "pay_method_crypto")
async def pay_method_crypto(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    if user_id not in user_payment:
        await callback.message.edit_text("Сессия истекла, начните заново.")
        return

    data = user_payment[user_id]
    plan_key = data["plan"]
    duration_key = data["duration"]
    price = data["price"]

    duration_names = {
        "month": "1 месяц",
        "3months": "3 месяца",
        "6months": "6 месяцев"
    }

    description = f"Premium VPN на {duration_names.get(duration_key, duration_key)}"
    payload = f"{user_id}:{plan_key}:{duration_key}"

    invoice = await cryptobot.create_invoice(
        amount_rub=price,
        description=description,
        payload=payload,
        paid_btn_url="https://t.me/streamnetvpnbot"
    )

    # Логируем, чтобы в случае чего было видно структуру ответа
    logger.info(f"CryptoBot invoice response for user {user_id}: {invoice}")

    back_kb = InlineKeyboardBuilder().row(
        InlineKeyboardButton(
            text="« Назад",
            callback_data=f"duration_{plan_key}_{duration_key}"
        )
    ).as_markup()

    if not invoice:
        await callback.message.edit_text(
            "❌ Ошибка создания счёта в CryptoBot. Попробуйте позже или выберите другой способ.",
            reply_markup=back_kb
        )
        return

    # Приоритет: Mini App → обычная ссылка на бота → web_app
    pay_url = (
        invoice.get("mini_app_invoice_url")
        or invoice.get("bot_invoice_url")
        or invoice.get("web_app_invoice_url")
    )

    if not pay_url:
        logger.error(f"CryptoBot invoice has no pay URL. Full response: {invoice}")
        await callback.message.edit_text(
            "❌ Не удалось получить ссылку на оплату. Попробуйте позже.",
            reply_markup=back_kb
        )
        return

    amount_rub = invoice.get("amount", price)

    text = (
        f"{emoji(EMOJI_MONEY, '💰')} <b>Стоимость:</b> <code>{amount_rub} ₽</code>\n"
        f"{emoji(EMOJI_CLOCK, '⏱️')} <b>Срок:</b> <code>{data['duration_label']}</code>\n\n"
        f"{emoji(EMOJI_BOLT, '⚡')} <b>Нажмите «Оплатить» для перехода к счёту.</b>"
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="Оплатить",
            url=pay_url
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Отмена",
            callback_data="pay_cancel"
        )
    )

    await callback.message.edit_text(
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
        disable_web_page_preview=True
    )


# ==================== Общая логика Platega ====================

async def create_platega_payment(message, user_id: int, payment_method: int):
    if user_id not in user_payment:
        await message.answer("Ошибка, попробуйте сначала")
        return

    data = user_payment[user_id]
    plan_key = data["plan"]
    duration_key = data["duration"]
    price = data["price"]

    method_name = "СБП" if payment_method == PLATEGA_METHOD_SBP else "Карта"
    logger.info(
        f"Platega: creating payment for user {user_id}, "
        f"method={method_name} ({payment_method}), amount={price}"
    )

    duration_names = {
        "month": "1 месяц",
        "3months": "3 месяца",
        "6months": "6 месяцев"
    }

    description = f"Оплата Premium на {duration_names.get(duration_key, duration_key)}"
    payload = f"{user_id}:{plan_key}:{duration_key}"
    return_url = "https://t.me/streamnetvpnbot"
    failed_url = "https://t.me/streamnetvpnbot"

    user = db.get_user(user_id)
    username = user.get("username") if user else None

    transaction = await platega.create_transaction(
        user_id=user_id,
        amount=price,
        description=description,
        return_url=return_url,
        failed_url=failed_url,
        payload=payload,
        payment_method=payment_method,
        username=username
    )

    logger.info(f"Platega full response for user {user_id}: {transaction}")

    back_kb = InlineKeyboardBuilder().row(
        InlineKeyboardButton(
            text="« Назад",
            callback_data=f"duration_{plan_key}_{duration_key}"
        )
    ).as_markup()

    if not transaction:
        await message.edit_text(
            "❌ Ошибка создания платежа. Попробуйте позже...",
            reply_markup=back_kb
        )
        return

    # Platega может вернуть "redirect" или "url" — проверяем оба
    redirect_url = transaction.get("redirect") or transaction.get("url")

    if not redirect_url:
        logger.error(f"Platega did not return redirect URL. Full response: {transaction}")
        await message.edit_text(
            "❌ Не удалось получить ссылку на оплату. Попробуйте позже.",
            reply_markup=back_kb
        )
        return

    user_transactions[user_id] = transaction.get("transactionId")

    await show_payment_confirmation(
        message,
        user_id,
        plan_key,
        duration_key,
        redirect_url
    )


async def show_payment_confirmation(message, user_id: int, plan_key: str, duration_key: str, redirect_url: str = None):
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
            f"{emoji(EMOJI_MONEY, '💰')} <b>Стоимость:</b> <code>{price} ₽</code>\n"
            f"{emoji(EMOJI_CLOCK, '⏱️')} <b>Срок:</b> <code>{label}</code>\n\n"
            f"<i>Нажимая «Оплатить» вы подтверждаете что ознакомились с "
            f'<a href="{privacy_url}">политикой конфиденциальности</a> и '
            f'<a href="{terms_url}">пользовательским соглашением</a>.</i>\n\n'
            f"{emoji(EMOJI_BOLT, '⚡')} <b>Нажмите «Оплатить» для перехода к оплате.</b>"
        )
    else:
        text = (
            f"{emoji(EMOJI_MONEY, '💰')} <b>Стоимость:</b> <code>{price} ₽</code>\n"
            f"{emoji(EMOJI_CLOCK, '⏱️')} <b>Срок:</b> <code>{label}</code>\n\n"
            f"{emoji(EMOJI_BOLT, '⚡')} <b>Нажмите «Оплатить» для перехода к оплате.</b>"
        )

    builder = InlineKeyboardBuilder()

    if redirect_url and isinstance(redirect_url, str) and redirect_url.startswith("http"):
        builder.row(
            InlineKeyboardButton(
                text="Оплатить",
                url=redirect_url
            )
        )
    else:
        logger.error(f"Invalid redirect_url for user {user_id}: {redirect_url}")
        await message.edit_text(
            "❌ Некорректная ссылка на оплату. Попробуйте позже.",
            reply_markup=InlineKeyboardBuilder().row(
                InlineKeyboardButton(
                    text="« Назад",
                    callback_data=f"duration_{plan_key}_{duration_key}"
                )
            ).as_markup()
        )
        return

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
async def pay_cancel(callback: CallbackQuery):
    user_id = callback.from_user.id

    if user_id in user_payment_messages:
        user_payment_messages.pop(user_id, None)

    user_payment.pop(user_id, None)
    user_transactions.pop(user_id, None)

    await pay_subscription(callback)