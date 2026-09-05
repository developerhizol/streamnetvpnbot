from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_about_service_keyboard():
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="Пользовательское соглашение",
        url="https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19",
        icon_custom_emoji_id="5257965810634202885"
    )
    
    builder.button(
        text="Политика конфиденциальности",
        url="https://telegra.ph/Politika-konfidencialnosti-06-21-31",
        icon_custom_emoji_id="5258476306152038031"
    )
 
    builder.button(text="« Назад", callback_data="back_to_menu")
    
    builder.adjust(1)
    return builder.as_markup()