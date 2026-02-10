import os
from flask import Flask, render_template, Response, request, jsonify
import requests
import aiomysql
from threading import Thread

# Loyihamizning boshqa qismlaridan kerakli narsalarni import qilamiz
# Eslatma: db_pool va get_db funksiyalari db.py faylidan keladi
# logger esa config.py dan keladi

# Flask ilovasini yaratamiz
app = Flask(__name__) 

# 1. ASOSIY SAHIFA
@app.route('/')
async def home():
    from db import get_db, db_pool # Importni ichkarida qilish 'circular import' xatosini oldini oladi
    from config import logger
    conn = None
    try:
        conn = await get_db() 
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT anime_id as id, name, poster_id FROM anime_list ORDER BY id DESC")
            animes = await cursor.fetchall()
            return render_template('aninovuz.html', animes=animes)
    except Exception as e:
        logger.error(f"Saytda xatolik: {e}")
        return f"Xatolik: {e}"
    finally:
        if conn:
            await db_pool.release(conn)

# 2. TELEGRAM RASMLARINI SAYTDA KO'RSATISH PROXYSI
@app.route('/image/<file_id>')
def get_telegram_image(file_id):
    from config import TOKEN
    try:
        file_info_url = f"https://api.telegram.org/bot{TOKEN}/getFile?file_id={file_id}"
        file_info = requests.get(file_info_url).json()
        if not file_info.get('ok'):
            return "Fayl topilmadi", 404
        file_path = file_info['result']['file_path']
        img_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
        img_res = requests.get(img_url)
        return Response(img_res.content, mimetype='image/jpeg')
    except Exception as e:
        return str(e), 500

# 3. XIZMATLAR SAHIFASI
@app.route('/services.html')
async def services():
    from db import get_db, db_pool
    from config import logger
    conn = None
    try:
        conn = await get_db()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT anime_id as id, name, poster_id FROM anime_list ORDER BY name ASC")
            all_animes = await cursor.fetchall()
            return render_template('services.html', animes=all_animes)
    except Exception as e:
        logger.error(f"Services sahifasida xato: {e}")
        return f"Xato: {e}"
    finally:
        if conn:
            await db_pool.release(conn)

# 4. ALOQA SAHIFASI
@app.route('/contact.html')
def contact():
    return render_template('contact.html')

# 5. MA'LUMOT/STATISTIKA SAHIFASI
@app.route('/malumot.html')
async def about():
    from db import get_db, db_pool
    from config import logger
    conn = None
    try:
        conn = await get_db()
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT COUNT(*) FROM anime_list")
            res = await cursor.fetchone()
            anime_count = res[0] if res else 0

            await cursor.execute("SELECT COUNT(*) FROM users")
            res = await cursor.fetchone()
            user_count = res[0] if res else 0

            await cursor.execute("SELECT COUNT(*) FROM users WHERE status = 'vip'")
            res = await cursor.fetchone()
            vip_count = res[0] if res else 0

            return render_template('malumot.html', 
                                   anime_count=anime_count, 
                                   user_count=user_count, 
                                   vip_count=vip_count)
    except Exception as e:
        logger.error(f"Statistika xatosi: {e}")
        return render_template('malumot.html', anime_count="0", user_count="0", vip_count="0")
    finally:
        if conn:
            await db_pool.release(conn)

# 6. VEB-SERVERNI ISHGA TUSHIRISH (Keep-Alive uchun)
def run():
    from config import logger
    port = int(os.environ.get("PORT", 10000))
    try:
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Flask server xatosi: {e}")

def keep_alive():
    t = Thread(target=run, daemon=True)
    t.start()

