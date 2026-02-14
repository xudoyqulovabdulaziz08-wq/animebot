from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
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
    return user, is_new
