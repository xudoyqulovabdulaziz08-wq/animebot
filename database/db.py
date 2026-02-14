import ssl
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from config import DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_NAME

# 1. SSL Kontekstini sozlash (Eski kodingizdagi sozlamalar)
def get_ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

# 2. Asinxron ulanish URLi
DATABASE_URL = f"mysql+aiomysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# 3. Engine yaratish (Pool sozlamalari bilan)
engine = create_async_engine(
    DATABASE_URL,
    connect_args={"ssl": get_ssl_context()},
    pool_size=20,           # Sizning maxsize=20 ga mos
    pool_recycle=300,        # Sizning pool_recycle=300 ga mos
    pool_pre_ping=True,      # Har doim ulanish tirikligini tekshiradi
    echo=False               # SQL so'rovlarni konsolda ko'rish uchun True qiling
)

# 4. Sessiyalar fabrikasi (Global db_pool o'rniga)
async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

# 5. Dependency (Handlerlar uchun sessiya yetkazib beruvchi)
async def get_db_session():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
          
