import sys
import os
import asyncio


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


from main import start_bot  # Botni ishga tushirish funksiyasi
 # Flask (app.py) obyekti
              # Flaskni asinxron ishga tushirish uchun



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
  




