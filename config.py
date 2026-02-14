import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", -5128040712))
MAIN_ADMIN_ID = int(os.getenv("ADMIN_ID", 8244870375))
ADVERTISING_PASSWORD = os.getenv("ADS_PASS")

# Ma'lumotlar bazasi parametrlari
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", 27624)
DB_NAME = os.getenv("DB_NAME")

# SQLAlchemy uchun asinxron ulanish URLi
# SSL parametrlari bilan (agar kerak bo'lsa)
DATABASE_URL = (
    f"mysql+aiomysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        f"?ssl=true" # SSL mode REQUIRED bo'lsa shunday qo'shiladi
        )
