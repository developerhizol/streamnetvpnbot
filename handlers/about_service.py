from aiogram import Router, F
from aiogram.types import CallbackQuery
from keyboards.about_service_keyboard import get_about_service_keyboard
from handlers.start import edit_main_menu

router = Router()

def emoji(emoji_id: str, fallback: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

@router.callback_query(F.data == "about")
async def about_handler(callback: CallbackQuery):
    globe_emoji = emoji("5879585266426973039", "🌐")
    
    text = (
        f"{globe_emoji} <b>Aura Network VPN - aura net</b>\n\n"
        f"Aura Network VPN обеспечивает стабильный и безопасный доступ к сети. "
        f"Мы используем современные протоколы с открытым исходным кодом, которые показывают "
        f"высокую скорость и устойчивость даже при работе в условиях строгих ограничений.\n\n"
        f"Подключение и управление сервисом полностью автоматизировано через Telegram, "
        f"поэтому доступ к нему всегда остаётся простым и удобным"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=get_about_service_keyboard(),
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