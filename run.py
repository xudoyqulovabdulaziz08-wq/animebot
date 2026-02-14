import sys
import os
import asyncio

# Loyiha yo'laklarini Python-ga tanitish
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# main.py ichidan faqat bot funksiyasini olamiz
from main import start_bot 


def run_dummy_server():
    """Render uchun yolg'onchi port ochuvchi funksiya"""
    port = int(os.environ.get("PORT", 8080))
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"📡 Dummy server {port}-portda ishlamoqda...")
        httpd.serve_forever()


async def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()
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








