import ssl
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from config import (
    DB_USER1, DB_PASS1, DB_HOST1, DB_PORT1, DB_NAME1,
    DB_USER2, DB_PASS2, DB_HOST2, DB_PORT2, DB_NAME2,
    DB_USER3, DB_PASS3, DB_HOST3, DB_PORT3, DB_NAME3,
    DB_USER4, DB_PASS4, DB_HOST4, DB_PORT4, DB_NAME4,
    DB_USER5, DB_PASS5, DB_HOST5, DB_PORT5, DB_NAME5,
    DB_USER6, DB_PASS6, DB_HOST6, DB_PORT6, DB_NAME6,
    DB_USER7, DB_PASS7, DB_HOST7, DB_PORT7, DB_NAME7
)

# 1. SSL Kontekstini sozlash
def get_ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

# 2. URL larni shakllantirish
def make_url(u, p, h, po, n):
    return f"mysql+aiomysql://{u}:{p}@{h}:{po}/{n}"

URLS = {
    "u1": make_url(DB_USER1, DB_PASS1, DB_HOST1, DB_PORT1, DB_NAME1),
    "u2": make_url(DB_USER2, DB_PASS2, DB_HOST2, DB_PORT2, DB_NAME2),
    "u3": make_url(DB_USER3, DB_PASS3, DB_HOST3, DB_PORT3, DB_NAME3),
    "a1": make_url(DB_USER4, DB_PASS4, DB_HOST4, DB_PORT4, DB_NAME4),
    "a2": make_url(DB_USER5, DB_PASS5, DB_HOST5, DB_PORT5, DB_NAME5),
    "a3": make_url(DB_USER6, DB_PASS6, DB_HOST6, DB_PORT6, DB_NAME6),
    "fb": make_url(DB_USER7, DB_PASS7, DB_HOST7, DB_PORT7, DB_NAME7),
}

# 3. Engine'lar va Sessiyalar lug'atini yaratish
engines = {}
session_factories = {}

ssl_ctx = get_ssl_context()

for key, url in URLS.items():
    engines[key] = create_async_engine(
        url,
        connect_args={"ssl": ssl_ctx},
        pool_size=20,
        pool_recycle=300,
        pool_pre_ping=True,
        echo=False
    )
    session_factories[key] = async_sessionmaker(
        bind=engines[key],
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False
    )

# 4. ROUTER FUNKSIYALARI (3+3+1 Mantiqi)

def get_user_session(user_id: int):
    """User ID oxirgi raqami bo'yicha: 0-3 (U1), 4-6 (U2), 7-9 (U3)"""
    last = int(str(user_id)[-1])
    if last <= 3: return session_factories["u1"]()
    if last <= 6: return session_factories["u2"]()
    return session_factories["u3"]()

def get_anime_session(name: str):
    """Anime nomi bo'yicha: A-I (A1), J-R (A2), S-Z+ (A3)"""
    if not name: return session_factories["a3"]()
    char = name[0].upper()
    if 'A' <= char <= 'I': return session_factories["a1"]()
    if 'J' <= char <= 'R': return session_factories["a2"]()
    return session_factories["a3"]()

def get_feedback_session():
    """Sharh va shikoyatlar uchun 7-baza"""
    return session_factories["fb"]()



async def init_databases():
    """Barcha 7 ta bazada jadvallarni yaratish"""
    from database.models import Base  # Modellarni import qilamiz
    
    print("⏳ Jadvallar yaratilmoqda, kuting...")
    
    for name, engine in engines.items():
        try:
            async with engine.begin() as conn:
                # Base.metadata ichida hamma jadvallar bor
                # U har bir bazada kerakli jadvallarni (users, anime_list va h.k.) yaratadi
                await conn.run_sync(Base.metadata.create_all)
            print(f"✅ Baza muvaffaqiyatli tayyorlandi: {name}")
        except Exception as e:
            print(f"❌ {name} bazasida xatolik: {e}")

    print("🚀 Barcha bazalar ishga tushishga tayyor!")


