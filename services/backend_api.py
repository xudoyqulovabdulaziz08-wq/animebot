import aiohttp
import logging
from config import config # Secret tokenlar va URL shu yerdan keladi

logger = logging.getLogger("BackendApiService")

class BackendApiService:
    @staticmethod
    async def get_web_password(user_id: int) -> Optional[str]:
        """
        Node.js backend bilan bog'lanib, foydalanuvchi uchun 
        shaxsiy kabinet parolini xavfsiz generatsiya qiladi.
        """
        # Node.js backend manzili va bot xavfsizlik kaliti (Secret Token)
        url = f"{config.BACKEND_INTERNAL_URL}/api/auth/bot/generate-password"
        headers = {
            "Authorization": f"Bearer {config.BOT_INTERNAL_SECRET_TOKEN}"
        }
        payload = {"userId": user_id}

        try:
            async with aiohttp.ClientSession() as session:
                async with asyncio.timeout(5.0): # So'rov qotib qolishini oldini olamiz
                    async with session.post(url, json=payload, headers=headers) as response:
                        if response.status == 200:
                            result = await response.json()
                            return result.get("password")
                        else:
                            logger.error(f"❌ Backend xatosi: Status {response.status}")
                            return None
        except Exception as e:
            logger.error(f"🚨 Backend ulanishida xatolik: {e}")
            return None