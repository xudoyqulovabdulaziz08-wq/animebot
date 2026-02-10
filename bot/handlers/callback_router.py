from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from handlers.common import get_user_status

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    # Foydalanuvchi statusini aniqlash
    status = await get_user_status(user_id)
    await query.answer()

    # 1. ADMIN CALLBACKLARI (adm_, manage_, del_ch_, conf_ kabi)
    if data.startswith(("adm_", "manage_", "del_ch_", "add_admin_", "rem_admin_", "conf_adm_", "conf_vip_")):
        from handlers.admin import admin_callback_handle
        return await admin_callback_handle(update, context, status)

    # 2. ANIME VA QIDIRUV CALLBACKLARI (ani_, selani_, search_, get_ep_ kabi)
    elif data.startswith(("ani_", "selani_", "search_", "get_ep_", "list_ani_", "viewani_", "addepto_")):
        from handlers.anime import anime_callback_handle
        return await anime_callback_handle(update, context)

    # 3. PAGINATION (SAHFALASH)
    elif data.startswith("pg_"):
        from handlers.admin import pagination_handler # Yoki umumiy joyda bo'lsa o'sha yerga
        return await pagination_handler(update, context)

    # 4. UMUMIY VA SOZLAMALAR (u_, back_ kabi)
    elif data.startswith(("u_", "recheck", "back_to_main")):
        from handlers.user import user_callback_handle
        return await user_callback_handle(update, context, status)
    
    # 5. Obunani qayta tekshirish (Common)
    if data == "recheck":
        from handlers.common import recheck_subscription_logic
        return await recheck_subscription_logic(update, context, status)

    return None