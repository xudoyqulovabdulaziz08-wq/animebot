import asyncio
import ssl
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from core import DATABASE_URL
from models import Base

# ================= CONFIG =================
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# ================= MIGRATION CORE =================
def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata
    )

    with context.begin_transaction():
        context.run_migrations()


# ================= ONLINE =================
async def run_migrations_online() -> None:
    url = str(DATABASE_URL)

    # sslmode ni olib tashlaymiz (asyncpg buni tanimaydi)
    if "sslmode=" in url:
        url = url.replace("?sslmode=require", "").replace("&sslmode=require", "")

    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = url

    # Aiven/Render uchun SSL tekshiruvini chetlab o'tish
    connect_args = {}
    if "localhost" not in url and "127.0.0.1" not in url:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        connect_args["ssl"] = ctx  # True o'rniga kontekstni beramiz

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


# ================= OFFLINE =================
def run_migrations_offline() -> None:
    url = str(DATABASE_URL)

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# ================= ENTRY =================
if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())