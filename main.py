from telegram import Update
from telegram.ext import Application, CommandHandler, ChatMemberHandler, ContextTypes
from config import BOT_TOKEN
from datetime import datetime

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👁️ 𝗠𝗔𝗧𝗔 𝗔𝗡𝗚𝗘𝗟\n\n"
        "Halo, saya Mata Angel.\n"
        "Mata-mata resmi AngelHub - @Halo_Angel\n\n"
        "Saya memantau:\n"
        "• Member Join / Leave\n"
        "• Ganti Nama / Username\n"
        "• Aktivitas Grup\n\n"
        "Grup aman karena diawasi Mata Angel."
    )

async def track_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    user = result.new_chat_member.user
    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status
    waktu = datetime.now().strftime("%H:%M WIB")

    if old_status in ["left", "kicked"] and new_status in ["member", "administrator"]:
        text = (
            f"👁️ 𝗠𝗔𝗧𝗔 𝗔𝗡𝗚𝗘𝗟 𝗠𝗘𝗡𝗗𝗘𝗧𝗘𝗞𝗦𝗜\n\n"
            f"👤 Nama: {user.full_name}\n"
            f"🆔 ID: {user.id}\n"
            f"📥 Status: BARU BERGABUNG\n"
            f"🕐 Waktu: {waktu}\n\n"
            f"Selamat datang di AngelHub."
        )
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text)

    elif new_status in ["left", "kicked"]:
        text = (
            f"👁️ 𝗠𝗔𝗧𝗔 𝗔𝗡𝗚𝗘𝗟 𝗠𝗘𝗡𝗗𝗘𝗧𝗘𝗞𝗦𝗜\n\n"
            f"👤 Nama: {user.full_name}\n"
            f"🆔 ID: {user.id}\n"
            f"📤 Status: MENINGGALKAN GRUP\n"
            f"🕐 Waktu: {waktu}"
        )
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(ChatMemberHandler(track_member, ChatMemberHandler.CHAT_MEMBER))
    print("Mata Angel Aktif...")
    app.run_polling()

if __name__ == "__main__":
    main()
