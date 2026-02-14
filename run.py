import http.server
import socketserver
import threading
import os
import asyncio
from main import start_bot

def run_dummy_server():
    """Render xatosi bermasligi uchun baquvvat dummy server"""
    # Render avtomatik beradigan PORT o'zgaruvchisini olamiz
    port = int(os.environ.get("PORT", 8080))
    
    # Oddiy so'rovlarga 200 OK qaytaruvchi handler
    class SimpleHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is running!")

    # 0.0.0.0 manzili Render uchun shart!
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", port), SimpleHandler) as httpd:
        print(f"📡 Dummy server 0.0.0.0:{port} manzilida Render uchun ochiq.")
        httpd.serve_forever()

async def main():
    # Dummy serverni alohida oqimda srazu ishga tushiramiz
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    print("🚀 Tizim ishga tushmoqda...")
    try:
        await start_bot()
    except Exception as e:
        print(f"❌ Xatolik yuz berdi: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Tizim to'xtatildi")
        










