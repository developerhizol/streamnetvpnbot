# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7752488661"))

# Web
PORT = int(os.getenv("PORT", "6382"))
SUBSCRIPTION_DOMAIN = os.getenv("SUBSCRIPTION_DOMAIN", "streamnetvpn.bothost.tech")
BOT_USERNAME = os.getenv("BOT_USERNAME", "streamnetvpnbot")

# Platega
PLATEGA_MERCHANT_ID = os.getenv("PLATEGA_MERCHANT_ID")
PLATEGA_SECRET = os.getenv("PLATEGA_SECRET")
PLATEGA_API_URL = "https://app.platega.io"

# SubGram
SUBGRAM_API_KEY = os.getenv("SUBGRAM_API_KEY")
SUBGRAM_API_URL = "https://api.subgram.org"

# CryptoBot
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")
CRYPTOBOT_API_URL = "https://pay.crypt.bot/api"

# Админка (логин/пароль)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
