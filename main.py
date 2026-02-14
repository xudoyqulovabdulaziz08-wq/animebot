from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from config import TOKEN
from db import engine
from handlers.user import start  # user.py ichidagi start funksiyasi

async def start_bot():
    """Botni sozlash va ishga tushirish funksiyasi"""
    
    # 1. Application-ni yaratish
    # Bu yerda biz botni barcha asinxron funksiyalari bilan yig'amiz
    application = ApplicationBuilder().token(TOKEN).build()

    # 2. Handlerlarni ro'yxatdan o'tkazish
    # Start buyrug'ini ulaymiz
    application.add_handler(CommandHandler("start", start))

    # Kelgusida boshqa handlerlarni ham shu yerga qo'shasiz:
    # application.add_handler(CommandHandler("help", help_handler))

    # 3. Botni ishga tushirish
    print("🤖 Bot polling rejimida ishlamoqda...")
    
    try:
        await application.initialize()
        await application.start()
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        
        # Bot to'xtamaguncha kutib turish
        # Bu run.py dagi asyncio.gather ichida ishlashi uchun muhim
        import asyncio
        while True:
            await asyncio.sleep(1)
            
    except Exception as e:
        print(f"❌ Bot ishga tushishida xatolik: {e}")
    finally:
        # Resurslarni tozalash (yopish)
        if application.running:
            await application.stop()
        if application.initialized:
            await application.shutdown()

# Agar kimdir main.py-ni o'zini yurgizib yuborsa (test uchun)
if __name__ == "__main__":
    import asyncio
    asyncio.run(start_bot())
