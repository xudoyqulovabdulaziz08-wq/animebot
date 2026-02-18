from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from database.models import User
from datetime import datetime
from config import MAIN_ADMIN_ID

async def register_user(session: AsyncSession, tg_user):
    """
    Ushbu funksiya router orqali tanlangan sessiya ichida ishlaydi.
    """
    stmt = select(User).where(User.user_id == tg_user.id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            user_id=tg_user.id,
            username=tg_user.username,
            status="user"
        )
        session.add(user)
        is_new = True
    else:
        # Foydalanuvchi username'ni o'zgartirgan bo'lsa yangilab qo'yamiz
        if user.username != tg_user.username:
            user.username = tg_user.username
        is_new = False
    
    await session.flush() # Ma'lumotni bazaga tayyorlab qo'yamiz (commit start-da bo'ladi)
    return user, is_new

async def get_user_status(session: AsyncSession, user_id: int, main_admin_id: int):
    """
    User statusini tekshirish.
    """
    if user_id == main_admin_id:
        return "main_admin"

    try:
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return "user"

        # VIP muddatini tekshirish
        if user.status == 'vip' and user.vip_expire_date:
            if datetime.now() > user.vip_expire_date:
                user.status = 'user'
                user.vip_expire_date = None
                await session.flush()
                return "user"

        return user.status
    except Exception as e:
        print(f"⚠️ Status aniqlashda xato: {e}")
        return "user"

    






