import sys
import os
import asyncio


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


from main import start_bot  # Botni ishga tushirish funksiyasi
from web.app import app     # Flask (app.py) obyekti
import uvicorn                  # Flaskni asinxron ishga tushirish uchun

async def run_flask():
    """Flaskni asinxron rejimda ishga tushirish"""
    # Render portni o'zi beradi, agar bo'lmasa 5000 ni oladi
    port = int(os.environ.get("PORT", 5000)) 
    config = uvicorn.Config(app, host="0.0.0.0", port=port, loop="asyncio")
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    """Bot va Web qismni parallel yurgizish"""
    print("🚀 Tizim ishga tushmoqda...")
    await asyncio.gather(
        start_bot(),
        run_flask()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Tizim to'xtatildi")
  



