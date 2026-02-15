from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from database.models import User
from datetime import datetime
from config import MAIN_ADMIN_ID

async def register_user(session: AsyncSession, tg_user):
    stmt = select(User).where(User.user_id == tg_user.id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            user_id=tg_user.id,
            username=tg_user.username,
            status="user",
            # joined_at ni tashlab ketsak ham bo'ladi (server_default bor)
        )
        session.add(user)
        is_new = True
    else:
        if user.username != tg_user.username:
            user.username = tg_user.username
        is_new = False
    
    # Commit-ni bitta joyda (asosan start funksiyasida) qilish xavfsizroq, 
    # lekin bu yerda qolsa ham flush ishlatish yaxshiroq
    await session.flush() 
    return user, is_new
    

async def get_user_status(session: AsyncSession, user_id: int, MAIN_ADMIN_ID: int):
    # 1. Avval yaratuvchini tekshiramiz (Bazaga kirmasdan)
    # Argument sifatida kelgan MAIN_ADMIN_ID dan foydalanamiz
    if user_id == MAIN_ADMIN_ID:
        return "main_admin"

    try:
        # 2. Foydalanuvchini bazadan qidiramiz
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return "user"

        # 3. VIP muddatini tekshirish
        if user.status == 'vip' and user.vip_expire_date:
            # Server vaqti bilan solishtirish
            if datetime.now() > user.vip_expire_date:
                user.status = 'user'
                user.vip_expire_date = None
                await session.flush() 
                return "user"

        return user.status
    except Exception as e:
        print(f"⚠️ Status aniqlashda xato: {e}")
        return "user"

    





