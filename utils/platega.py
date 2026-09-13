# utils/platega.py
import aiohttp
import logging
from typing import Optional, Dict, Any
from config import PLATEGA_MERCHANT_ID, PLATEGA_SECRET, PLATEGA_API_URL

logger = logging.getLogger(__name__)

# ID методов оплаты Platega
PLATEGA_METHOD_SBP = 2      # СБП / QR
PLATEGA_METHOD_CARD = 11    # Карточный эквайринг


class PlategaAPI:
    def __init__(self):
        self.merchant_id = PLATEGA_MERCHANT_ID
        self.secret = PLATEGA_SECRET
        self.base_url = PLATEGA_API_URL
        self.headers = {
            "X-MerchantId": self.merchant_id,
            "X-Secret": self.secret,
            "Content-Type": "application/json"
        }

    async def create_transaction(
        self,
        user_id: int,
        amount: int,
        description: str,
        return_url: str,
        failed_url: str,
        payload: str,
        payment_method: int = PLATEGA_METHOD_SBP,
        username: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Создаёт платёжную ссылку с указанным методом оплаты.
        payment_method: 2 — СБП, 11 — карта.
        """
        # Явно приводим к int на случай, если пришла строка
        payment_method = int(payment_method)

        data = {
            "paymentMethod": payment_method,
            "paymentDetails": {
                "amount": amount,
                "currency": "RUB"
            },
            "description": description,
            "return": return_url,
            "failedUrl": failed_url,
            "payload": payload,
            "metadata": {
                "userId": str(user_id),
                "userName": username or f"user_{user_id}"
            }
        }

        logger.info(
            f"Platega REQUEST: paymentMethod={payment_method}, "
            f"amount={amount}, description={description}, payload={payload}"
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/transaction/process",
                    headers=self.headers,
                    json=data,
                    timeout=30
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(
                            f"Platega RESPONSE: paymentMethod={result.get('paymentMethod')}, "
                            f"transactionId={result.get('transactionId')}, "
                            f"redirect={result.get('redirect') or result.get('url')}, "
                            f"status={result.get('status')}"
                        )
                        return result
                    else:
                        error_text = await response.text()
                        logger.error(f"Platega API error {response.status}: {error_text}")
                        return None
        except Exception as e:
            logger.error(f"Platega API exception: {e}")
            return None

    async def check_transaction(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/transaction/{transaction_id}",
                    headers=self.headers,
                    timeout=30
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Transaction status: {result.get('status')}")
                        return result
                    else:
                        error_text = await response.text()
                        logger.error(f"Platega check error {response.status}: {error_text}")
                        return None
        except Exception as e:
            logger.error(f"Platega check exception: {e}")
            return None


platega = PlategaAPI()