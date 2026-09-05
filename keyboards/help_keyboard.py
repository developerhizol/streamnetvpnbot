from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_help_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="« Назад", callback_data="back_to_menu")
    return builder.as_markup()