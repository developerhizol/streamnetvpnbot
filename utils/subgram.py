# utils/subgram.py
import aiohttp
import logging
from typing import Optional, Dict, Any, List
from config import SUBGRAM_API_KEY, SUBGRAM_API_URL

logger = logging.getLogger(__name__)

class SubGramAPI:
    def __init__(self):
        self.api_key = SUBGRAM_API_KEY
        self.base_url = SUBGRAM_API_URL
        self.headers = {
            "Auth": self.api_key,
            "Content-Type": "application/json"
        }
    
    async def get_sponsors(self, user_id: int, chat_id: int, get_links: bool = True) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            logger.warning("SUBGRAM_API_KEY not set")
            return None
        
        data = {
            "user_id": user_id,
            "chat_id": chat_id,
            "get_links": 1 if get_links else 0
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/get-sponsors",
                    headers=self.headers,
                    json=data,
                    timeout=30
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"SubGram get_sponsors for user {user_id}: {result.get('status')}")
                        return result
                    elif response.status == 404:
                        logger.info(f"User {user_id} has no sponsors (404)")
                        return None
                    else:
                        error_text = await response.text()
                        logger.error(f"SubGram API error {response.status}: {error_text}")
                        return None
        except Exception as e:
            logger.error(f"SubGram API exception: {e}")
            return None
    
    async def get_user_subscriptions(self, user_id: int, ads_ids: List[int] = None) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            logger.warning("SUBGRAM_API_KEY not set")
            return None
        
        data = {"user_id": user_id}
        if ads_ids:
            data["ads_ids"] = ads_ids
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/get-user-subscriptions",
                    headers=self.headers,
                    json=data,
                    timeout=30
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"SubGram get_user_subscriptions for user {user_id}: {result.get('status')}")
                        return result
                    elif response.status == 404:
                        # Нет спонсоров для пользователя — возвращаем None (означает "нет спонсоров")
                        logger.info(f"User {user_id} has no sponsors (404)")
                        return None
                    else:
                        error_text = await response.text()
                        logger.error(f"SubGram API error {response.status}: {error_text}")
                        return None
        except Exception as e:
            logger.error(f"SubGram API exception: {e}")
            return None
    
    async def check_subscription_status(self, user_id: int) -> bool:
        result = await self.get_user_subscriptions(user_id)
        
        # Если result is None — нет спонсоров, считаем что подписка активна
        if result is None:
            return True
        
        if result.get('status') != 'ok':
            return False
        
        sponsors = result.get('additional', {}).get('sponsors', [])
        if not sponsors:
            return True
        
        all_subscribed = all(s.get('status') == 'subscribed' for s in sponsors)
        return all_subscribed

subgram = SubGramAPI()