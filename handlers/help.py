# handlers/help.py
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from handlers.start import edit_main_menu

router = Router()

@router.callback_query(F.data == "help")
async def help_handler(callback: CallbackQuery):
    text = (
        "Если у вас появились <b>вопросы или возникли проблемы</b>, "
        "обратитесь в техническую поддержку сервиса <u>нажав на кнопку ниже</u>."
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="Тех. поддержка",
            url="https://t.me/StreamNetAdmin",
            icon_custom_emoji_id="5258093637450866522"
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
    await callback.answer()

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    first_name = callback.from_user.first_name
    username = callback.from_user.username
    
    await edit_main_menu(callback, user_id, first_name, username)
    await callback.answer()