import aiomysql
import ssl
import logging
from config import DB_CONFIG, logger

# ===================================================================================

# Global pool o'zgaruvchisi
db_pool = None

async def init_db_pool():
    global db_pool # Kichik harf bilan
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        db_pool = await aiomysql.create_pool(
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            db=DB_CONFIG['db'],
            autocommit=True,
            minsize=1, 
            maxsize=20,
            pool_recycle=300,
            charset='utf8mb4',
            cursorclass=aiomysql.DictCursor,
            ssl=ctx
        )
        
        # Jadvallarni yaratish (Asinxron rejimda)
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Foydalanuvchilar (VIP, Ballar, Sog'liq rejimi)
                await cur.execute("""CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY, 
                    username VARCHAR(255),
                    joined_at DATETIME, 
                    points INT DEFAULT 0,
                    status VARCHAR(20) DEFAULT 'user',
                    vip_expire_date DATETIME DEFAULT NULL,
                    health_mode TINYINT(1) DEFAULT 1,
                    referral_count INT DEFAULT 0
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

                # 2. Animelar (Reyting, Janr, Fandub, Ko'rilishlar)
                await cur.execute("""CREATE TABLE IF NOT EXISTS anime_list (
                    anime_id INT AUTO_INCREMENT PRIMARY KEY, 
                    name VARCHAR(255) NOT NULL, 
                    poster_id TEXT,
                    lang VARCHAR(100),
                    genre VARCHAR(255),
                    year VARCHAR(20),
                    fandub VARCHAR(255),
                    description TEXT,
                    rating_sum FLOAT DEFAULT 0,
                    rating_count INT DEFAULT 0,
                    views_week INT DEFAULT 0,
                    is_completed TINYINT(1) DEFAULT 0,
                    INDEX (name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

                # 3. Anime qismlari
                await cur.execute("""CREATE TABLE IF NOT EXISTS anime_episodes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    anime_id INT,
                    episode INT,
                    file_id TEXT,
                    FOREIGN KEY (anime_id) REFERENCES anime_list(anime_id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                
                # 4. Sevimli animelar
                await cur.execute("""CREATE TABLE IF NOT EXISTS favorites (
                    user_id BIGINT,
                    anime_id INT,
                    PRIMARY KEY (user_id, anime_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (anime_id) REFERENCES anime_list(anime_id)
                                  
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

                # 5. Korishlar tarixi
                await cur.execute("""CREATE TABLE IF NOT EXISTS history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT,
                    anime_id INT,
                    last_episode INT,
                    watched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (anime_id) REFERENCES anime_list(anime_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

                # 6. izohlar jadvali

                await cur.execute("""CREATE TABLE IF NOT EXISTS comments (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT,
                    anime_id INT,
                    comment_text TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (anime_id) REFERENCES anime_list(anime_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                # 7. Reklamalar boshqaruvi (14, 26-bandlar)
                await cur.execute("""CREATE TABLE IF NOT EXISTS advertisements (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    content_type VARCHAR(20), -- 'photo', 'video', 'text
                    file_id TEXT,
                    caption TEXT,
                    start_date DATETIME,
                    end_date DATETIME,
                    is_active TINYINT(1) DEFAULT 1
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

                #8 Shikoyatlar va Murojaatlar (20-band)
                await cur.execute("""CREATE TABLE IF NOT EXISTS feedback (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT,
                    subject VARCHAR(255),
                    message TEXT,
                    status VARCHAR(20) DEFAULT 'pending',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

                # 9. Donatlar va Moliyaviy statistika
                await cur.execute("""CREATE TABLE IF NOT EXISTS donations (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT,
                    amount DECIMAL(10,2),
                    donated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

                # 10. Kanallar
                await cur.execute("""CREATE TABLE IF NOT EXISTS channels (
                    username VARCHAR(255) PRIMARY KEY,
                    subscribers_added INT DEFAULT 0
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

                 # 11. Adminlar va harakatlar tarixi (21-band)
                await cur.execute("""CREATE TABLE IF NOT EXISTS admin_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    admin_id BIGINT,
                    action TEXT,
                    action_date DATETIME DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                # 28-BANDGA MOS QO'SHIMCHA: Sevimli janrlar (Shaxsiy tavsiyalar uchun)
                await cur.execute("""CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id BIGINT,
                    genre VARCHAR(100),
                    interest_level INT DEFAULT 1,
                    PRIMARY KEY (user_id, genre)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

        print("✅ Asinxron DB Pool yaratildi va jadvallar tayyor!")
    except Exception as e:
        logger.error(f"❌ DB Pool Error: {e}")

# ===================================================================================

async def get_db():
    global db_pool
    if db_pool is None:
        await init_db_pool()
    return await db_pool.acquire()

# ===================================================================================

async def execute_query(query, params=None, fetch="none"):
    """Bazaga so'rov yuborish uchun xavfsiz helper funksiya"""
    global db_pool
    # Pool mavjudligini tekshirish
    if db_pool is None:
        await init_db_pool()
        if db_pool is None:
            raise Exception("Ma'lumotlar bazasiga ulanib bo'lmadi!")

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params or ())
                if fetch == "one":
                    return await cur.fetchone()
                elif fetch == "all":
                    return await cur.fetchall()
                return cur.rowcount 
    except Exception as e:
        logger.error(f"❌ SQL Xatolik: {e} | Query: {query}")
        return None

async def create_fan_profile(user_id: int, bio: str, fav_genre: str):
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE users SET bio = %s, favorite_genre = %s WHERE user_id = %s",
                (bio, fav_genre, user_id)
            )


# ===================================================================================



