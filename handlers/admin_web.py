# handlers/admin_web.py
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, WebAppInfo, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import ADMIN_ID
from database import db
import logging
from pathlib import Path

router = Router()
logger = logging.getLogger(__name__)

ADMIN_PANEL_URL = "https://streamnetvpn.bothost.tech/admin"
ADMIN_IMAGE_PATH = Path(__file__).parent.parent / "imgs" / "admin.jpg"

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    if not ADMIN_IMAGE_PATH.exists():
        logger.error(f"Admin image not found: {ADMIN_IMAGE_PATH}")
        await message.answer("❌ Изображение не найдено")
        return
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="Открыть админку",
            web_app=WebAppInfo(url=ADMIN_PANEL_URL),
            style="primary"
        )
    )
    
    photo = FSInputFile(ADMIN_IMAGE_PATH)
    
    await message.answer_photo(
        photo=photo,
        caption="<b>Админ панель:</b>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )