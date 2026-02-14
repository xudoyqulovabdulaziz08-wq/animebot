import asyncio
from main import start_bot  # Botni ishga tushirish funksiyasi
from web.app import app     # Flask (app.py) obyekti
import uvicorn                  # Flaskni asinxron ishga tushirish uchun

async def run_flask():
    """Flaskni asinxron rejimda ishga tushirish"""
    config = uvicorn.Config(app, host="0.0.0.0", port=5000, loop="asyncio")
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
  

