import os
import logging

# Render Dashboard yoki .env fayldan olinadigan o'zgaruvchilar
TOKEN = os.getenv("TOKEN")
BOT_TOKEN = os.getenv("BOT_TOKEN") 
ADMIN_GROUP_ID = -5128040712 
MAIN_ADMIN_ID = int(os.getenv("ADMIN_ID", 8244870375))
ADVERTISING_PASSWORD = os.getenv("ADS_PASS", "2009")

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT", 27624)),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS"),
    "db": os.getenv("DB_NAME"), 
    "autocommit": True,
    "ssl_disabled": False, 
    "ssl_mode": "REQUIRED" 
}

# Loglash sozlamalari
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===================================================================================

