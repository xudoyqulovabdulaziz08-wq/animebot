from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from database.models import User
from datetime import datetime

async def register_user(session: AsyncSession, tg_user):
    """Foydalanuvchini bazaga xavfsiz qo'shish yoki ma'lumotlarini yangilash"""
    # Avval bazada borligini tekshiramiz
    stmt = select(User).where(User.user_id == tg_user.id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        # Yangi foydalanuvchi
        user = User(
            user_id=tg_user.id,
            username=tg_user.username,
            status="user",
            joined_at=datetime.now(),
            points=0,
            referral_count=0
        )
        session.add(user)
        is_new = True
    else:
        # Eski foydalanuvchi bo'lsa, username o'zgargan bo'lishi mumkin - yangilab qo'yamiz
        user.username = tg_user.username
        is_new = False
    
    # O'zgarishlarni saqlaymiz
    await session.commit()
    await session.refresh(user)
    return user, is_new

async def get_user_status(session, user_id: int, main_admin_id: int):
    """
    Foydalanuvchi statusini SQLAlchemy orqali tekshirish va yangilash.
    """
    # 1. Main Admin (Hardcoded)
    if user_id == main_admin_id:
        return "main_admin"

    try:
        # 2. Foydalanuvchini bazadan qidirish
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return "user"

        # 3. VIP muddatini tekshirish mantiqi
        if user.status == 'vip' and user.vip_expire_date:
            if datetime.now() > user.vip_expire_date:
                # Muddat tugagan bo'lsa, statusni tushirish
                user.status = 'user'
                user.vip_expire_date = None
                await session.commit()
                return "user"

        return user.status

    except Exception as e:
        print(f"⚠️ Status aniqlashda xato: {e}")
        return "user"
