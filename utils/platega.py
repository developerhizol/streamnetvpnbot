# utils/platega.py
import aiohttp
import logging
from typing import Optional, Dict, Any
from config import PLATEGA_MERCHANT_ID, PLATEGA_SECRET, PLATEGA_API_URL

logger = logging.getLogger(__name__)

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
        username: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Создаёт платёжную ссылку БЕЗ указания метода оплаты.
        Пользователь сам выберет способ на странице Platega.
        """
        data = {
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
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/v2/transaction/process",
                    headers=self.headers,
                    json=data,
                    timeout=30
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Platega transaction created: {result.get('transactionId')}")
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
                    f"{self.base_url}/v2/transaction/{transaction_id}",
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