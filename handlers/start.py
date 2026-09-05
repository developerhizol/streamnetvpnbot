# handlers/start.py
from aiogram import Router, Bot
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from datetime import datetime, timedelta
import locale
from database import db, get_moscow_time
from keyboards.main_menu import get_main_keyboard
from config import BOT_TOKEN

try:
    locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_TIME, 'ru_RU')
    except:
        pass

router = Router()
bot = Bot(token=BOT_TOKEN)

def emoji(emoji_id: str, fallback: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

def format_date(date: datetime) -> str:
    if not date:
        return "—"
    months = {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля",
        5: "мая", 6: "июня", 7: "июля", 8: "августа",
        9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
    }
    return f"{date.day} {months[date.month]} {date.year}г."

async def edit_main_menu(target, user_id: int, first_name: str, username: str = None):
    user = db.get_user(user_id)
    is_new = user is None

    if is_new:
        db.create_user(user_id, first_name, username)
    
    is_active = db.is_subscription_active(user_id)
    plan = db.get_user_plan(user_id)
    
    user_emoji = emoji("5258011929993026890", "👨‍🦱")
    
    # Получаем дату окончания подписки
    subscription_end = None
    if plan == "premium":
        sub_info = db.get_subscription_info(user_id)
        if sub_info:
            premium_until = sub_info.get('premium_until')
            if premium_until:
                if isinstance(premium_until, str):
                    premium_until = datetime.fromisoformat(premium_until)
                subscription_end = premium_until
    else:
        # Для Free тарифа показываем free_until если есть
        free_until = db.get_free_until(user_id)
        if free_until:
            if isinstance(free_until, str):
                free_until = datetime.fromisoformat(free_until)
            subscription_end = free_until
    
    # Формируем текст
    if plan == "premium" and is_active and subscription_end:
        end_date_str = format_date(subscription_end)
        text = (
            f"<blockquote>{user_emoji} <code>{first_name}  [{user_id}]</code></blockquote>\n\n"
            f"<b>Тариф:</b> Premium\n"
            f"<b>Подписка:</b> {end_date_str}"
        )
    else:
        text = (
            f"<blockquote>{user_emoji} <code>{first_name}  [{user_id}]</code></blockquote>\n\n"
            f"<b>Тариф:</b> Free"
        )

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(
            text,
            reply_markup=get_main_keyboard(user_id),
            parse_mode="HTML"
        )
    else:
        await target.answer(
            text,
            reply_markup=get_main_keyboard(user_id),
            parse_mode="HTML"
        )

@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username
    
    await edit_main_menu(message, user_id, first_name, username)