# utils/cryptobot.py
import aiohttp
import hashlib
import hmac
import logging
from typing import Optional, Dict, Any
from config import CRYPTOBOT_TOKEN

logger = logging.getLogger(__name__)

CRYPTOBOT_API_URL = "https://pay.crypt.bot/api"


class CryptoBotAPI:
    def __init__(self):
        self.token = CRYPTOBOT_TOKEN
        self.base_url = CRYPTOBOT_API_URL

    def _headers(self) -> dict:
        return {
            "Crypto-Pay-API-Token": self.token,
            "Content-Type": "application/json"
        }

    async def create_invoice(
        self,
        amount_rub: float,
        description: str,
        payload: str,
        paid_btn_url: str = "https://t.me/streamnetvpnbot",
        expires_in: int = 3600
    ) -> Optional[Dict[str, Any]]:
        """
        Создаёт инвойс в CryptoBot с оплатой в рублях (fiat).
        Возвращает объект с полями: invoice_id, bot_invoice_url, mini_app_invoice_url и т.д.
        """
        if not self.token:
            logger.error("CRYPTOBOT_TOKEN не задан")
            return None

        data = {
            "currency_type": "fiat",
            "fiat": "RUB",
            "amount": str(amount_rub),
            "description": description,
            "payload": payload,
            "paid_btn_name": "openBot",
            "paid_btn_url": paid_btn_url,
            "expires_in": expires_in
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/createInvoice",
                    headers=self._headers(),
                    json=data,
                    timeout=30
                ) as response:
                    result = await response.json()
                    if result.get("ok"):
                        invoice = result["result"]
                        logger.info(
                            f"CryptoBot invoice created: {invoice.get('invoice_id')}, "
                            f"amount={amount_rub} RUB"
                        )
                        return invoice
                    else:
                        logger.error(f"CryptoBot API error: {result}")
                        return None
        except Exception as e:
            logger.error(f"CryptoBot API exception: {e}")
            return None

    async def get_invoice(self, invoice_id: int) -> Optional[Dict[str, Any]]:
        """Получить информацию об инвойсе по ID."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/getInvoices",
                    headers=self._headers(),
                    params={"invoice_ids": str(invoice_id)},
                    timeout=30
                ) as response:
                    result = await response.json()
                    if result.get("ok") and result["result"]["items"]:
                        return result["result"]["items"][0]
                    return None
        except Exception as e:
            logger.error(f"CryptoBot get_invoice exception: {e}")
            return None

    @staticmethod
    def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
        """
        Проверяет подпись вебхука CryptoBot.
        Алгоритм:
          secret = SHA256(api_token)  (сырые байты)
          signature = HMAC-SHA256(secret, raw_body).hexdigest()
        """
        if not CRYPTOBOT_TOKEN or not signature:
            return False
        secret = hashlib.sha256(CRYPTOBOT_TOKEN.encode()).digest()
        computed = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(computed, signature)


cryptobot = CryptoBotAPI()