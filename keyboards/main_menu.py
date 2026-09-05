# keyboards/main_menu.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from database import db
import secrets

SUBSCRIPTION_DOMAIN = "streamnetvpn.bothost.tech"

def generate_token() -> str:
    return secrets.token_urlsafe(9)[:12]

def get_or_create_user_token(user_id: int) -> str:
    token = db.get_user_token(user_id)
    if not token:
        token = generate_token()
        db.save_user_token(user_id, token)
    return token

def get_main_keyboard(user_id: int = None) -> InlineKeyboardMarkup:
    token = None
    if user_id:
        token = get_or_create_user_token(user_id)
    
    btn_connect = InlineKeyboardButton(
        text="Подключить VPN",
        web_app=WebAppInfo(url=f"https://{SUBSCRIPTION_DOMAIN}/sub/{token}"),
        icon_custom_emoji_id="5323761960829862762"
    )
    
    plan = "free"
    if user_id:
        plan = db.get_user_plan(user_id)
    
    PREMIUM_BUY_EMOJI_ID = "5258185631355378853"
    PREMIUM_RENEW_EMOJI_ID = "5258258882022612173"
    
    if plan == "free":
        btn_pay = InlineKeyboardButton(
            text="Купить premium",
            callback_data="pay_subscription",
            style="primary",
            icon_custom_emoji_id=PREMIUM_BUY_EMOJI_ID
        )
    else:
        btn_pay = InlineKeyboardButton(
            text="Продлить premium",
            callback_data="pay_subscription",
            style="primary",
            icon_custom_emoji_id=PREMIUM_RENEW_EMOJI_ID
        )
    
    btn_profile = InlineKeyboardButton(
        text="Профиль",
        callback_data="profile",
        icon_custom_emoji_id="5260399854500191689"
    )
    
    btn_help = InlineKeyboardButton(
        text="Помощь",
        callback_data="help",
        icon_custom_emoji_id="5258503720928288433"
    )
    
    btn_about = InlineKeyboardButton(
        text="О сервисе",
        callback_data="about"
    )
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn_connect],
        [btn_pay],
        [btn_profile, btn_help],
        [btn_about]
    ])