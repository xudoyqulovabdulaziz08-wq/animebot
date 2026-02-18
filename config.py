import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", -5128040712))
MAIN_ADMIN_ID = int(os.getenv("ADMIN_ID", 8244870375))
ADVERTISING_PASSWORD = os.getenv("ADS_PASS")

# Ma'lumotlar bazasi parametrlari
DB_USER1 = os.getenv("DB_USER")
DB_PASS1 = os.getenv("DB_PASS")
DB_HOST1 = os.getenv("DB_HOST")
DB_PORT1 = os.getenv("DB_PORT", 27624)
DB_NAME1 = os.getenv("DB_NAME")

DB_USER2 = os.getenv("DB_USER2")
DB_PASS2 = os.getenv("DB_PASS2")
DB_HOST2 = os.getenv("DB_HOST2")
DB_PORT2 = os.getenv("DB_PORT2",20774 )
DB_NAME2 = os.getenv("DB_NAME2")

DB_USER3 = os.getenv("DB_USER3")
DB_PASS3 = os.getenv("DB_PASS3")
DB_HOST3 = os.getenv("DB_HOST3")
DB_PORT3 = os.getenv("DB_PORT3", 13487)
DB_NAME3 = os.getenv("DB_NAME3")

DB_USER4 = os.getenv("DB_USER4")
DB_PASS4 = os.getenv("DB_PASS4")
DB_HOST4 = os.getenv("DB_HOST4")
DB_PORT4 = os.getenv("DB_PORT4", 11621)
DB_NAME4 = os.getenv("DB_NAME4")

DB_USER5 = os.getenv("DB_USER5")
DB_PASS5 = os.getenv("DB_PASS5")
DB_HOST5 = os.getenv("DB_HOST5")    
DB_PORT5 = os.getenv("DB_PORT5", 26582)
DB_NAME5 = os.getenv("DB_NAME5")

DB_USER6 = os.getenv("DB_USER6")
DB_PASS6 = os.getenv("DB_PASS6")
DB_HOST6 = os.getenv("DB_HOST6")
DB_PORT6 = os.getenv("DB_PORT6", 15419)
DB_NAME6 = os.getenv("DB_NAME6")

DB_USER7 = os.getenv("DB_USER7")
DB_PASS7 = os.getenv("DB_PASS7")
DB_HOST7 = os.getenv("DB_HOST7")
DB_PORT7 = os.getenv("DB_PORT7", 21579)
DB_NAME7 = os.getenv("DB_NAME7")

DATABASE_URL = (
    f"mysql+aiomysql://{DB_USER1}:{DB_PASS1}@{DB_HOST1}:{DB_PORT1}/{DB_NAME1}"
        f"?ssl=true" # SSL mode REQUIRED bo'lsa shunday qo'shiladi
        )

DATABASE_URL2 = (
    f"mysql+aiomysql://{DB_USER2}:{DB_PASS2}@{DB_HOST2}:{DB_PORT2}/{DB_NAME2}"
        f"?ssl=true"
        )

DATABASE_URL3 = (
    f"mysql+aiomysql://{DB_USER3}:{DB_PASS3}@{DB_HOST3}:{DB_PORT3}/{DB_NAME3}"
        f"?ssl=true"       
        )

DATABASE_URL4 = (
    f"mysql+aiomysql://{DB_USER4}:{DB_PASS4}@{DB_HOST4}:{DB_PORT4}/{DB_NAME4}"
        f"?ssl=true"
        )

DATABASE_URL5 = (
    f"mysql+aiomysql://{DB_USER5}:{DB_PASS5}@{DB_HOST5}:{DB_PORT5}/{DB_NAME5}"
        f"?ssl=true"
        )

DATABASE_URL6 = (
    f"mysql+aiomysql://{DB_USER6}:{DB_PASS6}@{DB_HOST6}:{DB_PORT6}/{DB_NAME6}"
        f"?ssl=true"
        )

DATABASE_URL7 = (
    f"mysql+aiomysql://{DB_USER7}:{DB_PASS7}@{DB_HOST7}:{DB_PORT7}/{DB_NAME7}"
        f"?ssl=true"
        )

