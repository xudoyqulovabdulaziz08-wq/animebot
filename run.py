import sys
import os
import asyncio

# Loyiha yo'laklarini Python-ga tanitish
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# main.py ichidan faqat bot funksiyasini olamiz
from main import start_bot 

async def main():
    """Faqat Botni yurgizish mantiqi"""
    print("🚀 Tizim ishga tushmoqda...")
    try:
        # MUHIM: Bu yerda faqat start_bot() bo'lishi kerak!
        await start_bot()
    except Exception as e:
        print(f"❌ Xatolik yuz berdi: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Tizim to'xtatildi")







