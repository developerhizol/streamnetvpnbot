import asyncio
import logging
import secrets
import hashlib
import re
import json
import uuid
import aiohttp
import base64
import urllib.parse
from pathlib import Path
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import BOT_TOKEN, PLATEGA_MERCHANT_ID, PLATEGA_SECRET, SUBGRAM_API_KEY, SUBGRAM_API_URL
from database import db, get_moscow_time
from handlers import start_router, about_service_router, help_router, payment_router, profile_router, admin_router
from utils.admin_utils import get_servers_from_file, add_server_to_file, remove_server_from_file, clear_servers_file
from utils.subgram import subgram
from handlers.payment import PLANS, user_transactions, user_payment, user_payment_messages

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

PORT = 9283
SUBSCRIPTION_DOMAIN = "streamnetvpn.bothost.tech"
ADMIN_ID = 7752488661

BAN_EMOJI_ID = "5258318620722733379"
MAINTENANCE_EMOJI_ID = "6021401276904905698"
NEW_DEVICE_EMOJI_ID = "5445210909972655435"

def emoji(emoji_id: str, fallback: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

BAN_EMOJI = emoji(BAN_EMOJI_ID, "🚫")
MAINTENANCE_EMOJI = emoji(MAINTENANCE_EMOJI_ID, "🛠")
NEW_DEVICE_EMOJI = emoji(NEW_DEVICE_EMOJI_ID, "➕")

def deduplicate_sponsors(sponsors: list) -> list:
    unique = {}
    for s in sponsors:
        key = s.get('resource_id')
        if not key:
            key = s.get('ads_id')
        if not key:
            key = s.get('link', '')
        if key and key not in unique:
            unique[key] = s
    return list(unique.values())

def generate_token() -> str:
    return str(uuid.uuid4())

def get_or_create_user_token(user_id: int) -> str:
    token = db.get_user_token(user_id)
    if not token:
        token = generate_token()
        db.save_user_token(user_id, token)
    return token

def get_device_identifier(user_agent: str, ip: str, headers: dict = None) -> str:
    ua = user_agent or ''
    if headers:
        for key, value in headers.items():
            key_lower = key.lower()
            if key_lower in ['x-hwid', 'x-hw-id', 'x-device-id']:
                return value
    model = parse_device_model(ua)
    if model:
        return f"{model}_{ip}"
    return f"{ua}|{ip}"

def parse_device_model(user_agent: str) -> str:
    if not user_agent:
        return None
    ua = user_agent
    pattern = r'\(([A-Za-z0-9\s\-_]+);\s*Android'
    match = re.search(pattern, ua)
    if match:
        model = match.group(1).strip()
        model = re.sub(r'\s+', ' ', model)
        if model and len(model) > 2 and model not in ['K', 'L', 'M', 'N']:
            return model
    pattern2 = r'Android\s+[\d.]+\s*;\s*([A-Za-z0-9\s\-_]+?)(?:[;)])'
    match = re.search(pattern2, ua)
    if match:
        model = match.group(1).strip()
        model = re.sub(r'\s+', ' ', model)
        if model and len(model) > 2 and model not in ['K', 'L', 'M', 'N']:
            return model
    return None

def get_device_platform(user_agent: str) -> str:
    if not user_agent:
        return "Unknown"
    ua = user_agent.lower()
    if "android" in ua:
        return "Android"
    if "iphone" in ua or "ipad" in ua:
        return "iOS"
    if "macintosh" in ua:
        return "macOS"
    if "windows" in ua:
        return "Windows"
    if "linux" in ua:
        return "Linux"
    if "apple tv" in ua:
        return "tvOS"
    return "Unknown"

def pluralize_devices(count: int) -> str:
    if 11 <= count % 100 <= 19:
        return f"{count} устройств"
    elif count % 10 == 1:
        return f"{count} устройство"
    elif 2 <= count % 10 <= 4:
        return f"{count} устройства"
    else:
        return f"{count} устройств"

def get_device_display_name(user_agent: str, headers: dict = None) -> str:
    if headers:
        for key, value in headers.items():
            if key.lower() == 'x-device-model':
                return value
    model = parse_device_model(user_agent)
    if model:
        return model
    return "Неизвестное устройство"

def get_days_until_expiry(subscription_end) -> int:
    if not subscription_end:
        return 0
    if isinstance(subscription_end, str):
        subscription_end = datetime.fromisoformat(subscription_end)
    now = get_moscow_time()
    delta = subscription_end - now
    days = delta.days
    if days == 0 and delta.total_seconds() > 0:
        return 1
    return max(0, days)

def get_hours_until_expiry(subscription_end) -> int:
    if not subscription_end:
        return 0
    if isinstance(subscription_end, str):
        subscription_end = datetime.fromisoformat(subscription_end)
    now = get_moscow_time()
    delta = subscription_end - now
    return max(0, int(delta.total_seconds() / 3600))

def get_expire_timestamp(subscription_end) -> int:
    if not subscription_end:
        return 0
    if isinstance(subscription_end, str):
        subscription_end = datetime.fromisoformat(subscription_end)
    return int(subscription_end.timestamp())

def get_profile_headers(user_id: int) -> list:
    headers = ["#profile-title: 🚀 stream net"]
    if user_id != ADMIN_ID:
        headers.append("#hide-settings: 1")
    is_banned = db.is_user_banned(user_id)
    plan = db.get_user_plan(user_id)
    is_active = False
    if plan == "premium":
        is_active = db.check_premium_active(user_id)
    else:
        free_until = db.get_free_until(user_id)
        if free_until:
            if isinstance(free_until, str):
                free_until = datetime.fromisoformat(free_until)
            moscow_now = get_moscow_time()
            is_active = free_until > moscow_now
    if is_banned or not is_active:
        headers.append("#profile-update-interval: 1")
        headers.append("")
        return headers
    headers.append("#announce: base64:4pyC77iPIOKAlCDQsdC70L7QutC40YDRg9C10Lwg0YDQtdC60LvQsNC80YMg0L3QsCDRgdCw0LnRgtCw0YUgKNCx0LDQvdC90LXRgNGLLCDRgtGA0LXQutC10YDRiykK8J+boSDQpCDQvdC+0LLRi9C5INC/0YDQvtGC0L7QutC+0LsK4pqhIMKkINGB0LrQvtGA0L7RgdGC0L3QvtC5INC60LDQvdCw0LsK8J+MigrCpCDRgdGC0LDQvdC00LDRgNGC0L3Ri9C5INGB0LXRgNCy0LXRgArwn5SXIMKkINC60LDRgdC60LDQtCAo0KDQrS3QstGF0L7QtCDQpCDQt9Cw0YDRg9Cx0LXQttC90YvQuSDRgtC10YDRgtC10LvQuNGA0YPRjtGJ0LjRhSkK8J+nrSDCpCDQutCw0YHQutCw0LQg0YEg0LDQstGC0L7Qv9C+0LTQsdC+0YDQvtC8")
    headers.append("#profile-update-interval: 1")
    headers.append("")
    return headers

def get_config_for_user(user_id: int, device_id: str = None, device_name: str = None, token: str = None, is_subgram_ok: bool = None) -> str:
    is_banned = db.is_user_banned(user_id)
    plan = db.get_user_plan(user_id)
    is_active = False
    if plan == "premium":
        is_active = db.check_premium_active(user_id)
    else:
        free_until = db.get_free_until(user_id)
        if free_until:
            if isinstance(free_until, str):
                free_until = datetime.fromisoformat(free_until)
            moscow_now = get_moscow_time()
            is_active = free_until > moscow_now
    is_subgram_need_subscribe = False
    if plan == "free" and is_subgram_ok is not None:
        is_subgram_need_subscribe = not is_subgram_ok
    if is_banned:
        config_lines = [
            "#profile-title: 🚀 stream net",
            "#profile-update-interval: 1",
            "#hide-settings: 1",
            "",
            "vless://#🚫 Аккаунт заблокирован"
        ]
        return "\n".join(config_lines)
    if is_subgram_need_subscribe:
        config_lines = [
            "#profile-title: 🚀 stream net",
            "#profile-update-interval: 1",
            "#hide-settings: 1",
            "",
            "vless://#❌ Ваша подписка приостановлена",
            "vless://#Вы отписались от спонсоров",
            "vless://#Подпишитесь заново",
            "vless://#Бот: @streamnetvpnbot"
        ]
        return "\n".join(config_lines)
    if not is_active:
        config_lines = [
            "#profile-title: 🚀 stream net",
            "#profile-update-interval: 1",
            "#hide-settings: 1",
            "",
            "vless://#❌ Подписка истекла",
            "vless://#Для продления подпишитесь",
            "vless://#на новых спонсоров"
        ]
        return "\n".join(config_lines)
    config_lines = get_profile_headers(user_id)
    current_token = db.get_user_token(user_id)
    if token and token != current_token:
        config_lines.append("vless://#❌ Ключ неактивен")
        return "\n".join(config_lines)
    if device_id:
        if not db.device_exists(user_id, device_id):
            if db.is_device_limit_exceeded(user_id):
                limit = db.get_device_limit(user_id)
                config_lines.append("vless://#⚠️ Превышен лимит устройств")
                config_lines.append(f"vless://#Лимит: {pluralize_devices(limit)}")
                return "\n".join(config_lines)
        else:
            conn = db._get_connection()
            conn.execute(
                "UPDATE device_fingerprints SET last_seen = CURRENT_TIMESTAMP WHERE user_id = ? AND fingerprint = ?",
                (user_id, device_id)
            )
            conn.commit()
            conn.close()
    servers = get_servers_from_file()
    if servers:
        for server in servers:
            config_lines.append(server["full"])
    else:
        config_lines.append("# Серверы не найдены. Добавьте серверы в админ-панели.")
    return "\n".join(config_lines)

async def update_users_data(bot: Bot):
    while True:
        try:
            now = get_moscow_time()
            last_update = db.get_last_user_update_time()
            if (now - last_update).total_seconds() < 3600:
                await asyncio.sleep(300)
                continue
            logger.info("Начинаем обновление данных пользователей...")
            users = db.get_all_users()
            updated_count = 0
            error_count = 0
            for user_id in users:
                try:
                    try:
                        user_info = await bot.get_chat(user_id)
                        first_name = user_info.first_name or "Unknown"
                        username = user_info.username
                        current_user = db.get_user(user_id)
                        if current_user:
                            current_first_name = current_user.get('first_name')
                            current_username = current_user.get('username')
                            if current_first_name != first_name or current_username != username:
                                db.update_user_info(user_id, first_name, username)
                                updated_count += 1
                                logger.info(f"Обновлены данные пользователя {user_id}: {first_name} (@{username})")
                    except Exception as e:
                        error_count += 1
                        if error_count <= 5:
                            logger.error(f"Не удалось получить данные для пользователя {user_id}: {e}")
                        continue
                    await asyncio.sleep(0.05)
                except Exception as e:
                    error_count += 1
                    logger.error(f"Ошибка обновления данных пользователя {user_id}: {e}")
                    continue
            db.set_last_user_update_time(now)
            logger.info(f"Обновление данных пользователей завершено. Обновлено: {updated_count} пользователей, ошибок: {error_count}")
            await asyncio.sleep(3600)
        except Exception as e:
            logger.error(f"Ошибка в update_users_data: {e}")
            await asyncio.sleep(300)

async def check_subscriptions(bot: Bot):
    while True:
        try:
            users = db.get_all_users()
            now = get_moscow_time()
            for user_id in users:
                try:
                    user = db.get_user(user_id)
                    if not user:
                        continue
                    if not user.get('is_premium'):
                        continue
                    is_active = db.check_premium_active(user_id)
                    sub_info = db.get_subscription_info(user_id)
                    if not sub_info:
                        continue
                    premium_until = sub_info.get('premium_until')
                    if not premium_until:
                        continue
                    if isinstance(premium_until, str):
                        premium_until = datetime.fromisoformat(premium_until)
                    time_left = premium_until - now
                    hours_left = time_left.total_seconds() / 3600
                    if hours_left <= 24 and hours_left > 0 and sub_info.get('notify_24h_sent') == 0:
                        text = f"{emoji('5447621159719827951', '🔔')} <b>До конца вашей Premium подписки осталось менее 24 часов</b>\n\n{emoji('5444903695256941915', '💳')} <i>Продлите подписку чтобы не потерять доступ к серверам</i>"
                        builder = InlineKeyboardBuilder()
                        builder.row(
                            InlineKeyboardButton(
                                text="Продлить Premium",
                                callback_data="pay_subscription",
                                style="primary",
                                icon_custom_emoji_id="5258258882022612173"
                            )
                        )
                        try:
                            await bot.send_message(user_id, text, reply_markup=builder.as_markup(), parse_mode="HTML")
                            db.set_notify_24h_sent(user_id, 1)
                        except Exception as e:
                            logger.error(f"Ошибка отправки уведомления за 24 часа {user_id}: {e}")
                    if hours_left <= 1 and hours_left > 0 and sub_info.get('notify_1h_sent') == 0:
                        text = f"{emoji('5447621159719827951', '🔔')} <b>Ваша Premium подписка истекает через час!</b>\n\n{emoji('5444903695256941915', '💳')} <i>Продлите подписку чтобы не потерять доступ к серверам</i>"
                        builder = InlineKeyboardBuilder()
                        builder.row(
                            InlineKeyboardButton(
                                text="Продлить Premium",
                                callback_data="pay_subscription",
                                style="primary",
                                icon_custom_emoji_id="5258258882022612173"
                            )
                        )
                        try:
                            await bot.send_message(user_id, text, reply_markup=builder.as_markup(), parse_mode="HTML")
                            db.set_notify_1h_sent(user_id, 1)
                        except Exception as e:
                            logger.error(f"Ошибка отправки уведомления за 1 час {user_id}: {e}")
                    if not is_active and sub_info.get('notify_expired_sent') == 0:
                        text = f"{emoji('5447621159719827951', '🔔')} <b>Ваша Premium подписка истекла!</b>\n\n{emoji('5444903695256941915', '💳')} <i>Оплатите подписку чтобы восстановить доступ к серверам</i>"
                        builder = InlineKeyboardBuilder()
                        builder.row(
                            InlineKeyboardButton(
                                text="Оплатить Premium",
                                callback_data="pay_subscription",
                                style="primary",
                                icon_custom_emoji_id="5258258882022612173"
                            )
                        )
                        try:
                            await bot.send_message(user_id, text, reply_markup=builder.as_markup(), parse_mode="HTML")
                            db.set_notify_expired_sent(user_id, 1)
                        except Exception as e:
                            logger.error(f"Ошибка отправки уведомления об истечении {user_id}: {e}")
                    if hours_left > 24 and sub_info.get('notify_24h_sent') == 1:
                        db.set_notify_24h_sent(user_id, 0)
                    if hours_left > 1 and sub_info.get('notify_1h_sent') == 1:
                        db.set_notify_1h_sent(user_id, 0)
                    if is_active and sub_info.get('notify_expired_sent') == 1:
                        db.set_notify_expired_sent(user_id, 0)
                except Exception as e:
                    logger.error(f"Ошибка проверки подписки пользователя {user_id}: {e}")
                    continue
            await asyncio.sleep(300)
        except Exception as e:
            logger.error(f"Ошибка в check_subscriptions: {e}")
            await asyncio.sleep(300)

async def handle_token_info(request):
    token = request.match_info.get('token')
    conn = db._get_connection()
    row = conn.execute("SELECT user_id FROM user_tokens WHERE token = ?", (token,)).fetchone()
    conn.close()
    if not row:
        return web.json_response({"error": "Token not found"}, status=404)
    user_id = row['user_id']
    user = db.get_user(user_id)
    if not user:
        return web.json_response({"error": "User not found"}, status=404)
    is_active = False
    plan = db.get_user_plan(user_id)
    free_until = db.get_free_until(user_id)
    if plan == "premium":
        is_active = db.check_premium_active(user_id)
    else:
        if free_until:
            if isinstance(free_until, str):
                free_until = datetime.fromisoformat(free_until)
            moscow_now = get_moscow_time()
            is_active = free_until > moscow_now
    device_limit = db.get_device_limit(user_id)
    active_devices = db.get_active_devices_count(user_id)
    response_data = {
        "status": "active" if is_active else "inactive",
        "first_name": user.get('first_name', 'User'),
        "username": user.get('username', ''),
        "user_id": user_id,
        "expires_at": free_until.isoformat() if free_until else None,
        "plan": plan,
        "device_limit": device_limit,
        "active_devices": active_devices
    }
    return web.json_response(response_data)

def is_browser(user_agent: str) -> bool:
    if not user_agent:
        return True
    user_agent_lower = user_agent.lower()
    browser_keywords = [
        'mozilla', 'chrome', 'safari', 'firefox', 'opera', 'edge',
        'brave', 'vivaldi', 'yandex', 'trident', 'msie', 'webview',
        'android', 'iphone', 'ipad', 'macintosh', 'windows', 'linux'
    ]
    app_keywords = [
        'happ', 'v2raytun', 'nekobox', 'v2ray', 'clash', 'sing-box', 'shadowrocket',
        'stash', 'surge', 'quantumult', 'kitsunebi', 'postman', 'curl', 'wget'
    ]
    for keyword in app_keywords:
        if keyword in user_agent_lower:
            return False
    for keyword in browser_keywords:
        if keyword in user_agent_lower:
            return True
    return True

def is_mobile_app(user_agent: str) -> bool:
    if not user_agent:
        return False
    ua = user_agent.lower()
    supported_apps = ['happ', 'v2raytun', 'nekobox', 'v2ray', 'clash', 'sing-box', 'shadowrocket', 'stash', 'surge', 'quantumult', 'kitsunebi']
    for app in supported_apps:
        if app in ua:
            return True
    return False

def is_bot(user_agent: str) -> bool:
    if not user_agent:
        return False
    ua = user_agent.lower()
    bot_keywords = ['telegrambot', 'twitterbot', 'bot/', 'spider', 'crawler']
    for keyword in bot_keywords:
        if keyword in ua:
            return True
    return False

async def send_new_device_notification(bot: Bot, user_id: int, device_name: str, platform: str, os_version: str):
    try:
        if platform and os_version:
            device_info = f"{device_name} ({platform} {os_version})"
        elif platform:
            device_info = f"{device_name} ({platform})"
        else:
            device_info = device_name
        text = f"{NEW_DEVICE_EMOJI} <b>Подключено новое устройство: <u>{device_info}</u></b>"
        await bot.send_message(user_id, text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления о новом устройстве {user_id}: {e}")

async def serve_index():
    index_path = Path(__file__).parent / 'public' / 'index.html'
    if not index_path.exists():
        return web.Response(text="index.html not found", status=404)
    with open(index_path, 'r', encoding='utf-8') as f:
        html = f.read()
    return web.Response(text=html, content_type='text/html')

async def serve_check():
    check_path = Path(__file__).parent / 'public' / 'check.html'
    if not check_path.exists():
        return web.Response(text="check.html not found", status=404)
    with open(check_path, 'r', encoding='utf-8') as f:
        html = f.read()
    return web.Response(text=html, content_type='text/html')

async def handle_proxy_image(request):
    try:
        url = request.query.get('url')
        if not url:
            return web.Response(status=400, text="Missing url parameter")
        allowed_domains = [
            'img.subgram.ru', 'telegra.ph', 't.me', 'telegram.org', 'cdn.telegram.org',
            'i.ibb.co', 'imgur.com', 'i.imgur.com', 'avatars.githubusercontent.com',
            'raw.githubusercontent.com', 'cdn.discordapp.com', 'media.discordapp.net',
            'lh3.googleusercontent.com', 'drive.google.com'
        ]
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]
        is_allowed = any(allowed in domain for allowed in allowed_domains)
        if not is_allowed:
            logger.warning(f"Blocked image proxy request to: {domain}")
            return web.Response(status=403, text="Domain not allowed")
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    content_type = resp.headers.get('Content-Type', 'image/jpeg')
                    return web.Response(
                        body=data,
                        content_type=content_type,
                        headers={
                            'Cache-Control': 'no-cache, no-store, must-revalidate',
                            'Access-Control-Allow-Origin': '*'
                        }
                    )
                else:
                    logger.error(f"Failed to fetch image: {resp.status}")
                    return web.Response(status=resp.status, text="Failed to fetch image")
    except Exception as e:
        logger.error(f"Proxy image error: {e}")
        return web.Response(status=500, text=str(e))

async def handle_sub(request):
    token = request.match_info.get('token', '')
    if not token:
        return web.json_response({"error": "Access denied"}, status=403)
    
    user_agent = request.headers.get('User-Agent', '')
    client_ip = request.headers.get('X-Forwarded-For', request.remote)
    
    conn = db._get_connection()
    row = conn.execute("SELECT user_id FROM user_tokens WHERE token = ?", (token,)).fetchone()
    conn.close()
    
    if not row:
        if is_browser(user_agent):
            return await serve_index()
        return web.Response(text="Invalid token", status=403)
    
    user_id = row['user_id']
    
    if is_browser(user_agent):
        plan = db.get_user_plan(user_id)
        if plan == "free" and SUBGRAM_API_KEY:
            try:
                subscriptions = await subgram.get_user_subscriptions(user_id)
                if subscriptions is None:
                    return await serve_index()
                if subscriptions.get('status') == 'error':
                    return await serve_index()
                if subscriptions.get('status') != 'ok':
                    return await serve_index()
                sponsors = subscriptions.get('additional', {}).get('sponsors', [])
                if sponsors:
                    unique_sponsors = deduplicate_sponsors(sponsors)
                    need_subscribe = [
                        s for s in unique_sponsors
                        if s.get('status') == 'unsubscribed' and s.get('available_now') == True
                    ]
                    if need_subscribe:
                        return await serve_check()
                return await serve_index()
            except Exception as e:
                logger.error(f"SubGram check error for user {user_id}: {e}")
                return await serve_index()
        return await serve_index()
    
    headers_dict = {}
    for key, value in request.headers.items():
        headers_dict[key] = value
    
    hwid = None
    model = None
    platform = None
    os_version = None
    
    for key, value in headers_dict.items():
        key_lower = key.lower()
        if key_lower in ['x-hwid', 'x-hw-id', 'x-device-id']:
            hwid = value
        elif key_lower == 'x-device-model':
            model = value
        elif key_lower == 'x-device-os':
            platform = value
        elif key_lower == 'x-ver-os':
            os_version = value
    
    if not platform:
        platform = get_device_platform(user_agent)
    
    if is_bot(user_agent):
        config_text = get_config_for_user(user_id, None, None, token)
        return web.Response(text=config_text, headers={'Content-Type': 'text/plain'})
    
    if not is_mobile_app(user_agent):
        return web.Response(text="Ошибка: подписка доступна только в приложениях Happ или V2RayTun", status=403)
    
    is_subgram_ok = None
    plan = db.get_user_plan(user_id)
    
    if plan == "free" and SUBGRAM_API_KEY:
        try:
            subscriptions = await subgram.get_user_subscriptions(user_id)
            if subscriptions is None:
                is_subgram_ok = True
            elif subscriptions.get('status') == 'error':
                is_subgram_ok = True
            elif subscriptions.get('status') != 'ok':
                is_subgram_ok = True
            else:
                sponsors = subscriptions.get('additional', {}).get('sponsors', [])
                if sponsors:
                    unique_sponsors = deduplicate_sponsors(sponsors)
                    need_subscribe = [
                        s for s in unique_sponsors
                        if s.get('status') == 'unsubscribed' and s.get('available_now') == True
                    ]
                    is_subgram_ok = len(need_subscribe) == 0
                else:
                    is_subgram_ok = True
        except Exception as e:
            logger.error(f"SubGram check error for user {user_id}: {e}")
            is_subgram_ok = True
    
    device_id = get_device_identifier(user_agent, client_ip, headers_dict)
    device_name = get_device_display_name(user_agent, headers_dict)
    
    if not db.device_exists(user_id, device_id):
        if db.is_device_limit_exceeded(user_id):
            config_text = get_config_for_user(user_id, device_id, device_name, token, is_subgram_ok)
            return web.Response(text=config_text, headers={'Content-Type': 'text/plain'})
        db.register_device_fingerprint(user_id, device_id, device_name, platform, platform, os_version)
        from handlers.start import bot
        await send_new_device_notification(bot, user_id, device_name, platform, os_version)
    else:
        conn = db._get_connection()
        conn.execute(
            "UPDATE device_fingerprints SET last_seen = CURRENT_TIMESTAMP WHERE user_id = ? AND fingerprint = ?",
            (user_id, device_id)
        )
        conn.commit()
        conn.close()
    
    config_text = get_config_for_user(user_id, device_id, device_name, token, is_subgram_ok)
    response_headers = {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0',
        'Content-Type': 'text/plain'
    }
    if user_id != ADMIN_ID:
        response_headers['hide-settings'] = '1'
        response_headers['X-Hide-Settings'] = '1'
        response_headers['Hide-Settings'] = '1'
    
    return web.Response(text=config_text, headers=response_headers)

async def handle_check_subscription(request):
    token = request.match_info.get('token', '')
    if not token:
        return web.json_response({"error": "Access denied"}, status=403)
    
    conn = db._get_connection()
    row = conn.execute("SELECT user_id FROM user_tokens WHERE token = ?", (token,)).fetchone()
    conn.close()
    
    if not row:
        return web.json_response({"error": "Invalid token"}, status=403)
    
    user_id = row['user_id']
    
    try:
        sponsors_data = await subgram.get_sponsors(user_id, user_id)
        if sponsors_data is None:
            new_free_until = db.extend_free_subscription(user_id, days=3)
            db.update_subgram_linked(user_id, 1)
            return web.json_response({
                "status": "ok",
                "message": "Доступ открыт",
                "sponsors": [],
                "free_until": new_free_until.isoformat() if new_free_until else None
            })
        if sponsors_data.get('status') == 'error':
            new_free_until = db.extend_free_subscription(user_id, days=3)
            db.update_subgram_linked(user_id, 1)
            return web.json_response({
                "status": "ok",
                "message": "Доступ открыт",
                "sponsors": [],
                "free_until": new_free_until.isoformat() if new_free_until else None
            })
        if sponsors_data.get('status') != 'warning':
            new_free_until = db.extend_free_subscription(user_id, days=3)
            db.update_subgram_linked(user_id, 1)
            return web.json_response({
                "status": "ok",
                "message": "Доступ открыт",
                "sponsors": [],
                "free_until": new_free_until.isoformat() if new_free_until else None
            })
        sponsors = sponsors_data.get('additional', {}).get('sponsors', [])
        if not sponsors:
            new_free_until = db.extend_free_subscription(user_id, days=3)
            db.update_subgram_linked(user_id, 1)
            return web.json_response({
                "status": "ok",
                "message": "Доступ открыт",
                "sponsors": [],
                "free_until": new_free_until.isoformat() if new_free_until else None
            })
        unique_sponsors = deduplicate_sponsors(sponsors)
        need_subscribe = [
            s for s in unique_sponsors
            if s.get('status') == 'unsubscribed' and s.get('available_now') == True
        ]
        if not need_subscribe:
            new_free_until = db.extend_free_subscription(user_id, days=3)
            db.update_subgram_linked(user_id, 1)
            return web.json_response({
                "status": "ok",
                "message": "Вы подписаны на всех спонсоров",
                "sponsors": [],
                "free_until": new_free_until.isoformat() if new_free_until else None
            })
        return web.json_response({
            "status": "warning",
            "message": "Подпишитесь на спонсоров",
            "sponsors": need_subscribe
        })
    except Exception as e:
        logger.error(f"Error checking subscription for user {user_id}: {e}")
        new_free_until = db.extend_free_subscription(user_id, days=3)
        return web.json_response({
            "status": "ok",
            "message": "Доступ открыт",
            "sponsors": [],
            "free_until": new_free_until.isoformat() if new_free_until else None
        })

async def handle_confirm_subscription(request):
    token = request.match_info.get('token', '')
    if not token:
        return web.json_response({"error": "Access denied"}, status=403)
    
    conn = db._get_connection()
    row = conn.execute("SELECT user_id FROM user_tokens WHERE token = ?", (token,)).fetchone()
    conn.close()
    
    if not row:
        return web.json_response({"error": "Invalid token"}, status=403)
    
    user_id = row['user_id']
    
    try:
        subscriptions = await subgram.get_user_subscriptions(user_id)
        if subscriptions is None:
            new_free_until = db.extend_free_subscription(user_id, days=3)
            db.update_subgram_linked(user_id, 1)
            return web.json_response({
                "success": True,
                "message": "Доступ открыт!",
                "free_until": new_free_until.isoformat() if new_free_until else None
            })
        if subscriptions.get('status') == 'error':
            new_free_until = db.extend_free_subscription(user_id, days=3)
            db.update_subgram_linked(user_id, 1)
            return web.json_response({
                "success": True,
                "message": "Доступ открыт!",
                "free_until": new_free_until.isoformat() if new_free_until else None
            })
        if subscriptions.get('status') != 'ok':
            new_free_until = db.extend_free_subscription(user_id, days=3)
            db.update_subgram_linked(user_id, 1)
            return web.json_response({
                "success": True,
                "message": "Доступ открыт!",
                "free_until": new_free_until.isoformat() if new_free_until else None
            })
        sponsors = subscriptions.get('additional', {}).get('sponsors', [])
        if not sponsors:
            new_free_until = db.extend_free_subscription(user_id, days=3)
            db.update_subgram_linked(user_id, 1)
            return web.json_response({
                "success": True,
                "message": "Доступ открыт!",
                "free_until": new_free_until.isoformat() if new_free_until else None
            })
        unique_sponsors = deduplicate_sponsors(sponsors)
        need_subscribe = [
            s for s in unique_sponsors
            if s.get('status') == 'unsubscribed' and s.get('available_now') == True
        ]
        if not need_subscribe:
            new_free_until = db.extend_free_subscription(user_id, days=3)
            db.update_subgram_linked(user_id, 1)
            return web.json_response({
                "success": True,
                "message": "Подписка подтверждена! Доступ открыт на 3 дня.",
                "free_until": new_free_until.isoformat() if new_free_until else None
            })
        else:
            return web.json_response({
                "success": False,
                "message": "Вы подписались не на всех спонсоров"
            })
    except Exception as e:
        logger.error(f"Error confirming subscription for user {user_id}: {e}")
        new_free_until = db.extend_free_subscription(user_id, days=3)
        return web.json_response({
            "success": True,
            "message": "Доступ открыт!",
            "free_until": new_free_until.isoformat() if new_free_until else None
        })

async def handle_subgram_webhook(request):
    try:
        api_key = request.headers.get('Api-Key')
        if api_key != SUBGRAM_API_KEY:
            return web.Response(status=401)
        data = await request.json()
        webhooks = data.get('webhooks', [])
        processed_users = set()
        for webhook in webhooks:
            user_id = webhook.get('user_id')
            status = webhook.get('status')
            if not user_id:
                continue
            if user_id in processed_users:
                continue
            if status == 'unsubscribed':
                logger.info(f"User {user_id} unsubscribed from sponsor")
                with db._get_connection() as conn:
                    conn.execute("""
                        UPDATE users SET free_until = ? WHERE user_id = ?
                    """, (get_moscow_time() - timedelta(days=1), user_id))
                    conn.commit()
                from handlers.start import bot
                try:
                    text = f"{emoji('5447621159719827951', '🔔')} <b>Вы отписались от спонсоров!</b>\n\nВаш доступ к VPN приостановлен. Подпишитесь заново чтобы восстановить доступ."
                    await bot.send_message(user_id, text, parse_mode="HTML")
                    processed_users.add(user_id)
                except Exception as e:
                    logger.error(f"Error sending unsubscription notification to {user_id}: {e}")
        return web.Response(status=200, text="OK")
    except Exception as e:
        logger.error(f"SubGram webhook error: {e}")
        return web.Response(status=500)

async def handle_platega_webhook(request):
    try:
        merchant_id = request.headers.get('X-MerchantId')
        secret = request.headers.get('X-Secret')
        if merchant_id != PLATEGA_MERCHANT_ID or secret != PLATEGA_SECRET:
            return web.Response(status=401)
        data = await request.json()
        transaction_id = data.get('id')
        status = data.get('status')
        payload = data.get('payload')
        if status == "CONFIRMED" and payload:
            try:
                parts = payload.split(':')
                if len(parts) == 3:
                    user_id = int(parts[0])
                    plan_key = parts[1]
                    duration_key = parts[2]
                    plan = PLANS[plan_key]
                    duration_days = {
                        "month": plan["days_month"],
                        "3months": plan["days_3months"],
                        "6months": plan["days_6months"]
                    }
                    days = duration_days.get(duration_key, 30)
                    db.activate_premium(user_id, days=days)
                    price = db.get_price(plan_key, duration_key)
                    db.log_payment(user_id, price)
                    db.log_premium_purchase(user_id, price)
                    if user_id in user_transactions:
                        user_transactions.pop(user_id, None)
                    if user_id in user_payment:
                        user_payment.pop(user_id, None)
                    from handlers.start import bot
                    if user_id in user_payment_messages:
                        try:
                            await bot.delete_message(user_id, user_payment_messages[user_id])
                            user_payment_messages.pop(user_id, None)
                        except Exception as e:
                            logger.error(f"Error deleting payment message for user {user_id}: {e}")
                    text = (
                        f"{emoji('5447242579827523388', '✅')} <b>Оплата получена!</b>\n\n"
                        f"На ваш баланс было начислено {days} дней доступа тарифа «{plan['name']}».\n\n"
                        f"{emoji('5444887644964159628', '♥')} <b>Спасибо за покупку :)</b>"
                    )
                    builder = InlineKeyboardBuilder()
                    builder.row(
                        InlineKeyboardButton(
                            text="Главное меню",
                            callback_data="back_to_menu",
                            icon_custom_emoji_id="5257963315258204021"
                        )
                    )
                    try:
                        await bot.send_message(user_id, text, reply_markup=builder.as_markup(), parse_mode="HTML")
                    except Exception as e:
                        logger.error(f"Error sending payment notification to user {user_id}: {e}")
            except Exception as e:
                logger.error(f"Error processing webhook payload: {e}")
        return web.Response(status=200, text="OK")
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return web.Response(status=500)

async def handle_admin_login(request):
    try:
        data = await request.json()
        username = data.get('username')
        password = data.get('password')
        if db.check_admin_credentials(username, password):
            admin_id = db.get_admin_id(username)
            session_token = hashlib.sha256(f"{username}{password}{datetime.now().isoformat()}".encode()).hexdigest()[:32]
            db.log_admin_action(admin_id, "login", details=f"Успешный вход")
            return web.json_response({"success": True, "token": session_token})
        else:
            return web.json_response({"success": False, "error": "Неверный логин или пароль"}, status=401)
    except Exception as e:
        logger.error(f"Admin login error: {e}")
        return web.json_response({"success": False, "error": "Ошибка авторизации"}, status=500)

async def handle_admin_stats(request):
    try:
        auth_token = request.headers.get('X-Admin-Token')
        if not auth_token:
            return web.json_response({"error": "Unauthorized"}, status=401)
        page = int(request.query.get('page', 1))
        per_page = int(request.query.get('per_page', 10))
        offset = (page - 1) * per_page
        total_users = db.get_user_count()
        users = db.get_all_users_with_details(limit=per_page, offset=offset)
        stats = db.get_stats()
        return web.json_response({
            "total_users": stats['total_users'],
            "today_users": stats['today_users'],
            "week_users": stats['week_users'],
            "month_users": stats['month_users'],
            "today_payments": stats['today_payments'],
            "week_payments": stats['week_payments'],
            "month_payments": stats['month_payments'],
            "total_payments": stats['total_payments'],
            "today_sales": stats['today_sales'],
            "week_sales": stats['week_sales'],
            "month_sales": stats['month_sales'],
            "total_sales": stats['total_sales'],
            "users": users,
            "total": total_users,
            "page": page,
            "per_page": per_page,
            "total_pages": (total_users + per_page - 1) // per_page
        })
    except Exception as e:
        logger.error(f"Admin stats error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def handle_admin_user(request):
    try:
        auth_token = request.headers.get('X-Admin-Token')
        if not auth_token:
            return web.json_response({"error": "Unauthorized"}, status=401)
        user_id = int(request.match_info.get('user_id'))
        user = db.get_user(user_id)
        if not user:
            return web.json_response({"error": "User not found"}, status=404)
        is_active = db.is_subscription_active(user_id)
        is_banned = db.is_user_banned(user_id)
        plan = db.get_user_plan(user_id)
        free_until = db.get_free_until(user_id)
        return web.json_response({
            "user_id": user_id,
            "first_name": user.get('first_name', 'Unknown'),
            "username": user.get('username'),
            "plan": plan,
            "is_active": is_active,
            "is_banned": is_banned,
            "subscription_end": free_until.isoformat() if free_until else None,
        })
    except ValueError:
        return web.json_response({"error": "Invalid user_id"}, status=400)
    except Exception as e:
        logger.error(f"Admin user error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def handle_admin_user_avatar(request):
    try:
        auth_token = request.headers.get('X-Admin-Token')
        if not auth_token:
            return web.json_response({"error": "Unauthorized"}, status=401)
        user_id = int(request.match_info.get('user_id'))
        user = db.get_user(user_id)
        if not user:
            return web.json_response({"error": "User not found"}, status=404)
        from handlers.start import bot
        try:
            photos = await bot.get_user_profile_photos(user_id, limit=1)
            if photos.total_count > 0:
                photo = photos.photos[0][-1]
                file = await bot.get_file(photo.file_id)
                file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
                timeout = aiohttp.ClientTimeout(total=15)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(file_url) as resp:
                        if resp.status == 200:
                            file_data = await resp.read()
                            content_type = resp.headers.get('Content-Type', 'image/jpeg')
                            return web.Response(body=file_data, content_type=content_type)
                        else:
                            return web.json_response({"success": False, "error": f"Failed to download avatar: {resp.status}"}, status=404)
            else:
                return web.json_response({"success": False, "error": "No avatar"}, status=404)
        except Exception as e:
            logger.error(f"Ошибка получения аватарки для пользователя {user_id}: {e}")
            return web.json_response({"error": str(e)}, status=404)
    except Exception as e:
        logger.error(f"Admin avatar error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def handle_admin_servers(request):
    try:
        auth_token = request.headers.get('X-Admin-Token')
        if not auth_token:
            return web.json_response({"error": "Unauthorized"}, status=401)
        servers = get_servers_from_file()
        return web.json_response({"servers": servers})
    except Exception as e:
        logger.error(f"Admin servers error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def handle_admin_servers_add(request):
    try:
        auth_token = request.headers.get('X-Admin-Token')
        if not auth_token:
            return web.json_response({"error": "Unauthorized"}, status=401)
        data = await request.json()
        servers = data.get('servers', [])
        added = 0
        for server in servers:
            if server.strip():
                add_server_to_file(server.strip())
                added += 1
        return web.json_response({"success": True, "added": added})
    except Exception as e:
        logger.error(f"Admin servers add error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def handle_admin_servers_remove(request):
    try:
        auth_token = request.headers.get('X-Admin-Token')
        if not auth_token:
            return web.json_response({"error": "Unauthorized"}, status=401)
        data = await request.json()
        server_id = data.get('server_id')
        remove_server_from_file(server_id)
        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"Admin servers remove error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def handle_admin_servers_clear(request):
    try:
        auth_token = request.headers.get('X-Admin-Token')
        if not auth_token:
            return web.json_response({"error": "Unauthorized"}, status=401)
        clear_servers_file()
        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"Admin servers clear error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def handle_admin_prices(request):
    try:
        auth_token = request.headers.get('X-Admin-Token')
        if not auth_token:
            return web.json_response({"error": "Unauthorized"}, status=401)
        prices = db.get_all_prices()
        return web.json_response({"prices": prices})
    except Exception as e:
        logger.error(f"Admin prices error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def handle_admin_prices_set(request):
    try:
        auth_token = request.headers.get('X-Admin-Token')
        if not auth_token:
            return web.json_response({"error": "Unauthorized"}, status=401)
        data = await request.json()
        plan_key = data.get('plan_key')
        duration_key = data.get('duration_key')
        price = data.get('price')
        if not plan_key or not duration_key or price is None:
            return web.json_response({"error": "Missing parameters"}, status=400)
        db.set_price(plan_key, duration_key, int(price))
        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"Admin prices set error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def handle_admin_ban(request):
    try:
        auth_token = request.headers.get('X-Admin-Token')
        if not auth_token:
            return web.json_response({"error": "Unauthorized"}, status=401)
        data = await request.json()
        user_id = data.get('user_id')
        db.ban_user(user_id)
        db.log_admin_action(1, "ban", target_user_id=user_id, details=f"Пользователь {user_id} забанен")
        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"Admin ban error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def handle_admin_unban(request):
    try:
        auth_token = request.headers.get('X-Admin-Token')
        if not auth_token:
            return web.json_response({"error": "Unauthorized"}, status=401)
        data = await request.json()
        user_id = data.get('user_id')
        db.unban_user(user_id)
        db.log_admin_action(1, "unban", target_user_id=user_id, details=f"Пользователь {user_id} разбанен")
        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"Admin unban error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def handle_admin_give_premium(request):
    try:
        auth_token = request.headers.get('X-Admin-Token')
        if not auth_token:
            return web.json_response({"error": "Unauthorized"}, status=401)
        data = await request.json()
        user_id = data.get('user_id')
        days = data.get('days', 30)
        if db.check_premium_active(user_id):
            return web.json_response({"error": "User already has active premium"}, status=400)
        db.activate_premium(user_id, days=days)
        db.log_admin_action(1, "give_premium", target_user_id=user_id, details=f"Выдан Premium на {days} дней")
        from handlers.start import bot
        try:
            await bot.send_message(user_id, f"{emoji('6023940002008799618', '👑')} <b>Администратор выдал вам Premium подписку на {days} дней!</b>", parse_mode="HTML")
        except Exception:
            pass
        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"Admin give premium error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def handle_admin_take_premium(request):
    try:
        auth_token = request.headers.get('X-Admin-Token')
        if not auth_token:
            return web.json_response({"error": "Unauthorized"}, status=401)
        data = await request.json()
        user_id = data.get('user_id')
        if not db.check_premium_active(user_id):
            return web.json_response({"error": "У пользователя нет активной подписки"}, status=400)
        db.disable_premium(user_id)
        db.log_admin_action(1, "take_premium", target_user_id=user_id, details=f"Забрана Premium подписка у пользователя {user_id}")
        from handlers.start import bot
        try:
            await bot.send_message(user_id, f"{emoji('6021852682262682598', '👎')} <b>Администратор забрал у вас Premium подписку</b>", parse_mode="HTML")
        except Exception:
            pass
        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"Admin take premium error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def handle_admin_maintenance(request):
    try:
        auth_token = request.headers.get('X-Admin-Token')
        if not auth_token:
            return web.json_response({"error": "Unauthorized"}, status=401)
        data = await request.json()
        enabled = data.get('enabled', False)
        db.set_maintenance_mode(enabled)
        db.log_admin_action(1, "maintenance", details=f"Тех. перерыв: {enabled}")
        return web.json_response({"success": True, "enabled": enabled})
    except Exception as e:
        logger.error(f"Admin maintenance error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def handle_admin_maintenance_status(request):
    try:
        auth_token = request.headers.get('X-Admin-Token')
        if not auth_token:
            return web.json_response({"error": "Unauthorized"}, status=401)
        enabled = db.get_maintenance_mode()
        return web.json_response({"enabled": enabled})
    except Exception as e:
        logger.error(f"Admin maintenance status error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def handle_admin_broadcast(request):
    try:
        auth_token = request.headers.get('X-Admin-Token')
        if not auth_token:
            return web.json_response({"error": "Unauthorized"}, status=401)
        data = await request.json()
        broadcast_type = data.get('type', 'custom')
        message_data = data.get('message_data', {})
        db.log_admin_action(1, "broadcast", details=f"Рассылка отправлена, тип: {broadcast_type}")
        maintenance_mode = db.get_maintenance_mode()
        from handlers.start import bot
        if maintenance_mode:
            try:
                admin_id = ADMIN_ID
                text = message_data.get('text', '')
                buttons = message_data.get('buttons', [])
                media = message_data.get('media')
                builder = InlineKeyboardBuilder()
                current_row = []
                for idx, btn in enumerate(buttons):
                    color = btn.get('color', 'primary')
                    style_map = {
                        'primary': 'primary',
                        'success': 'success',
                        'danger': 'danger',
                        'default': 'default'
                    }
                    if btn.get('emoji_id'):
                        current_row.append(InlineKeyboardButton(
                            text=btn.get('text', ''),
                            url=btn.get('url', '#'),
                            style=style_map.get(color, 'primary'),
                            icon_custom_emoji_id=btn.get('emoji_id')
                        ))
                    else:
                        current_row.append(InlineKeyboardButton(
                            text=btn.get('text', ''),
                            url=btn.get('url', '#'),
                            style=style_map.get(color, 'primary')
                        ))
                    if len(current_row) == 2 or idx == len(buttons) - 1:
                        builder.row(*current_row)
                        current_row = []
                if media:
                    data_url = media.get('data')
                    if data_url:
                        header, encoded = data_url.split(',', 1)
                        file_data = base64.b64decode(encoded)
                        ext = 'jpg'
                        if 'image/png' in header:
                            ext = 'png'
                        elif 'image/gif' in header:
                            ext = 'gif'
                        elif 'video/mp4' in header:
                            ext = 'mp4'
                        input_file = BufferedInputFile(file_data, filename=f"broadcast.{ext}")
                        if media.get('type') == 'video':
                            await bot.send_video(
                                admin_id,
                                video=input_file,
                                caption=text if text else None,
                                reply_markup=builder.as_markup() if builder.buttons else None,
                                parse_mode="HTML" if text else None
                            )
                        else:
                            await bot.send_photo(
                                admin_id,
                                photo=input_file,
                                caption=text if text else None,
                                reply_markup=builder.as_markup() if builder.buttons else None,
                                parse_mode="HTML" if text else None
                            )
                    else:
                        await bot.send_message(admin_id, text, reply_markup=builder.as_markup() if builder.buttons else None, parse_mode="HTML")
                else:
                    await bot.send_message(admin_id, text, reply_markup=builder.as_markup() if builder.buttons else None, parse_mode="HTML")
                return web.json_response({"success": True, "mode": "maintenance", "sent_to_admin": True})
            except Exception as e:
                logger.error(f"Error sending broadcast to admin: {e}")
                return web.json_response({"error": str(e)}, status=500)
        users = db.get_all_users()
        sent_count = 0
        for user_id in users:
            try:
                if broadcast_type == 'custom':
                    text = message_data.get('text', '')
                    buttons = message_data.get('buttons', [])
                    media = message_data.get('media')
                    builder = InlineKeyboardBuilder()
                    current_row = []
                    for idx, btn in enumerate(buttons):
                        color = btn.get('color', 'primary')
                        style_map = {
                            'primary': 'primary',
                            'success': 'success',
                            'danger': 'danger',
                            'default': 'default'
                        }
                        if btn.get('emoji_id'):
                            current_row.append(InlineKeyboardButton(
                                text=btn.get('text', ''),
                                url=btn.get('url', '#'),
                                style=style_map.get(color, 'primary'),
                                icon_custom_emoji_id=btn.get('emoji_id')
                            ))
                        else:
                            current_row.append(InlineKeyboardButton(
                                text=btn.get('text', ''),
                                url=btn.get('url', '#'),
                                style=style_map.get(color, 'primary')
                            ))
                        if len(current_row) == 2 or idx == len(buttons) - 1:
                            builder.row(*current_row)
                            current_row = []
                    if media:
                        data_url = media.get('data')
                        if data_url:
                            header, encoded = data_url.split(',', 1)
                            file_data = base64.b64decode(encoded)
                            ext = 'jpg'
                            if 'image/png' in header:
                                ext = 'png'
                            elif 'image/gif' in header:
                                ext = 'gif'
                            elif 'video/mp4' in header:
                                ext = 'mp4'
                            input_file = BufferedInputFile(file_data, filename=f"broadcast.{ext}")
                            if media.get('type') == 'video':
                                await bot.send_video(
                                    user_id,
                                    video=input_file,
                                    caption=text if text else None,
                                    reply_markup=builder.as_markup() if builder.buttons else None,
                                    parse_mode="HTML" if text else None
                                )
                            else:
                                await bot.send_photo(
                                    user_id,
                                    photo=input_file,
                                    caption=text if text else None,
                                    reply_markup=builder.as_markup() if builder.buttons else None,
                                    parse_mode="HTML" if text else None
                                )
                        else:
                            await bot.send_message(user_id, text, reply_markup=builder.as_markup() if builder.buttons else None, parse_mode="HTML")
                    else:
                        await bot.send_message(user_id, text, reply_markup=builder.as_markup() if builder.buttons else None, parse_mode="HTML")
                else:
                    if message_data.get('type') == 'text':
                        await bot.send_message(user_id, message_data.get('content', ''), parse_mode="HTML")
                sent_count += 1
                await asyncio.sleep(0.05)
            except Exception as e:
                logger.error(f"Broadcast error to {user_id}: {e}")
        return web.json_response({"success": True, "sent": sent_count})
    except Exception as e:
        logger.error(f"Admin broadcast error: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def handle_admin_page(request):
    admin_path = Path(__file__).parent / 'public' / 'admin.html'
    if not admin_path.exists():
        return web.Response(text="admin.html not found", status=404)
    with open(admin_path, 'r', encoding='utf-8') as f:
        html = f.read()
    return web.Response(text=html, content_type='text/html')

async def start_webapp():
    app = web.Application()
    app._client_max_size = None
    
    app.router.add_get('/api/token/{token}', handle_token_info)
    app.router.add_get('/sub/{token}', handle_sub)
    app.router.add_get('/check/{token}', serve_check)
    app.router.add_get('/sub/check/{token}', handle_check_subscription)
    app.router.add_post('/sub/confirm/{token}', handle_confirm_subscription)
    app.router.add_get('/', handle_sub)
    app.router.add_post('/webhook/platega', handle_platega_webhook)
    app.router.add_post('/webhook/subgram', handle_subgram_webhook)
    app.router.add_get('/proxy/image', handle_proxy_image)
    
    app.router.add_post('/api/admin/login', handle_admin_login)
    app.router.add_get('/api/admin/stats', handle_admin_stats)
    app.router.add_get('/api/admin/user/{user_id}', handle_admin_user)
    app.router.add_get('/api/admin/user/{user_id}/avatar', handle_admin_user_avatar)
    app.router.add_get('/api/admin/servers', handle_admin_servers)
    app.router.add_post('/api/admin/servers/add', handle_admin_servers_add)
    app.router.add_post('/api/admin/servers/remove', handle_admin_servers_remove)
    app.router.add_post('/api/admin/servers/clear', handle_admin_servers_clear)
    app.router.add_get('/api/admin/prices', handle_admin_prices)
    app.router.add_post('/api/admin/prices/set', handle_admin_prices_set)
    app.router.add_post('/api/admin/ban', handle_admin_ban)
    app.router.add_post('/api/admin/unban', handle_admin_unban)
    app.router.add_post('/api/admin/give_premium', handle_admin_give_premium)
    app.router.add_post('/api/admin/take_premium', handle_admin_take_premium)
    app.router.add_get('/api/admin/maintenance', handle_admin_maintenance_status)
    app.router.add_post('/api/admin/maintenance', handle_admin_maintenance)
    app.router.add_post('/api/admin/broadcast', handle_admin_broadcast)
    app.router.add_get('/admin', handle_admin_page)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()

async def get_banned_message() -> str:
    return f"{BAN_EMOJI} <b>Вы были заблокированы.</b>\n\nЕсли считаете, что ваш бан был необоснованным, свяжитесь с администрацией @StreamNetAdmin."

async def get_banned_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="Связаться с админом",
            url="https://t.me/StreamNetAdmin",
            style="primary"
        )
    )
    return builder

from aiogram import BaseMiddleware
from typing import Callable, Dict, Any, Awaitable

class BanMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[types.Message, Dict[str, Any]], Awaitable[Any]],
        event: types.Message,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        if isinstance(event, (types.Message, types.CallbackQuery)):
            user_id = event.from_user.id
        if user_id:
            if db.is_user_banned(user_id) and user_id != ADMIN_ID:
                text = await get_banned_message()
                builder = await get_banned_keyboard()
                if isinstance(event, types.Message):
                    await event.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
                elif isinstance(event, types.CallbackQuery):
                    await event.answer("🚫 Вы заблокированы", show_alert=True)
                return
            maintenance_mode = db.get_maintenance_mode()
            if maintenance_mode and user_id != ADMIN_ID:
                if isinstance(event, types.Message):
                    text = f"{MAINTENANCE_EMOJI} <b>Бот на техническом перерыве...</b>\n\nПожалуйста, зайдите позже. Приносим извинения за неудобства."
                    await event.answer(text, parse_mode="HTML")
                elif isinstance(event, types.CallbackQuery):
                    await event.answer("🛠 Бот на техническом перерыве...", show_alert=True)
                return
        return await handler(event, data)

def main():
    db._init_db()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def run_all():
        await start_webapp()
        bot = Bot(token=BOT_TOKEN)
        asyncio.create_task(update_users_data(bot))
        asyncio.create_task(check_subscriptions(bot))
        from handlers.start import bot as start_bot
        start_bot = bot
        dp = Dispatcher()
        dp.message.middleware(BanMiddleware())
        dp.callback_query.middleware(BanMiddleware())
        dp.include_router(start_router)
        dp.include_router(about_service_router)
        dp.include_router(help_router)
        dp.include_router(payment_router)
        dp.include_router(profile_router)
        dp.include_router(admin_router)
        await dp.start_polling(bot)
    
    try:
        loop.run_until_complete(run_all())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()

if __name__ == "__main__":
    main()