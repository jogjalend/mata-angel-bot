from fastapi import FastAPI, Request
from telegram import Update as TgUpdate
from telegram.ext import Application, CommandHandler, ChatMemberHandler, MessageHandler, ContextTypes, filters
from datetime import datetime
import os

BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Database sementara (di memori, karena Vercel stateless)
db_users = {}
db_messages = {}

async def start(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👁️ 𝗠𝗔𝗧𝗔 𝗔𝗡𝗚𝗘𝗟\n\n"
        "Halo, saya Mata Angel.\n"
        "Mata-mata resmi AngelHub - @Halo_Angel\n\n"
        "Saya memantau:\n"
        "• Member Join / Leave\n"
        "• Ganti Nama / Username\n"
        "• Pesan Dihapus (log)\n\n"
        "Grup aman karena diawasi Mata Angel."
    )

async def mata_on(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👁️ Mata Angel DIAKTIFKAN. Semua aktivitas dipantau.")

async def mata_off(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👁️ Mata Angel DINONAKTIFKAN.")

async def laporan(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👁️ 𝗟𝗔𝗣𝗢𝗥𝗔𝗡 𝗠𝗔𝗧𝗔 𝗔𝗡𝗚𝗘𝗟\n\n"
        f"Total Member Terpantau: {len(db_users)}\n"
        f"Total Pesan Tersimpan: {len(db_messages)}\n"
        f"Waktu: {datetime.now().strftime('%d %B %Y - %H:%M WIB')}\n\n"
        f"— AngelHub"
    )

async def track_member(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    user = result.new_chat_member.user
    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status
    waktu = datetime.now().strftime("%H:%M WIB")
    chat_id = update.effective_chat.id
    user_id = str(user.id)

    old_data = db_users.get(user_id, {})

    # Cek Ganti Nama
    if old_data and (old_data.get("name") != user.full_name or old_data.get("username") != user.username):
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"👁️ 𝗠𝗔𝗧𝗔 𝗔𝗡𝗚𝗘𝗟 𝗠𝗘𝗡𝗗𝗘𝗧𝗘𝗞𝗦𝗜\n\n👤 Sebelumnya: {old_data.get('name')} - @{old_data.get('username')}\n👤 Sekarang: {user.full_name} - @{user.username}\n🔄 Status: GANTI IDENTITAS\n🕐 Waktu: {waktu}"
        )

    db_users[user_id] = {"name": user.full_name, "username": user.username}

    # Join
    if old_status in ["left", "kicked"] and new_status in ["member", "administrator"]:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"👁️ 𝗠𝗔𝗧𝗔 𝗔𝗡𝗚𝗘𝗟 𝗠𝗘𝗡𝗗𝗘𝗧𝗘𝗞𝗦𝗜\n\n👤 Nama: {user.full_name}\n🆔 ID: {user.id}\n📥 Status: BARU BERGABUNG\n🕐 Waktu: {waktu}\n\nSelamat datang di AngelHub."
        )
    # Leave
    elif new_status in ["left", "kicked"]:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"👁️ 𝗠𝗔𝗧𝗔 𝗔𝗡𝗚𝗘𝗟 𝗠𝗘𝗡𝗗𝗘𝗧𝗘𝗞𝗦𝗜\n\n👤 Nama: {user.full_name}\n🆔 ID: {user.id}\n📤 Status: MENINGGALKAN GRUP\n🕐 Waktu: {waktu}"
        )

async def save_message(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return

    db_messages[str(msg.message_id)] = {
        "user": msg.from_user.full_name,
        "username": msg.from_user.username,
        "text": msg.text,
        "time": datetime.now().strftime("%H:%M WIB")
    }

    user_id = str(msg.from_user.id)
    old = db_users.get(user_id, {})
    if old and (old.get("name") != msg.from_user.full_name or old.get("username") != msg.from_user.username):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"👁️ 𝗠𝗔𝗧𝗔 𝗔𝗡𝗚𝗘𝗟 𝗠𝗘𝗡𝗗𝗘𝗧𝗘𝗞𝗦𝗜\n\n👤 Sebelumnya: {old.get('name')} - @{old.get('username')}\n👤 Sekarang: {msg.from_user.full_name} - @{msg.from_user.username}\n🔄 Status: GANTI IDENTITAS"
        )

    db_users[user_id] = {"name": msg.from_user.full_name, "username": msg.from_user.username}

# --- Setup Bot ---
ptb_app = Application.builder().token(BOT_TOKEN).build()
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CommandHandler("mata_on", mata_on))
ptb_app.add_handler(CommandHandler("mata_off", mata_off))
ptb_app.add_handler(CommandHandler("laporan", laporan))
ptb_app.add_handler(ChatMemberHandler(track_member, ChatMemberHandler.CHAT_MEMBER))
ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_message))

# --- FastAPI untuk Vercel ---
web_app = FastAPI()

@web_app.post("/api/index")
async def webhook(request: Request):
    data = await request.json()
    update = TgUpdate.de_json(data, ptb_app.bot)
    await ptb_app.initialize()
    await ptb_app.process_update(update)
    return {"ok": True}

@web_app.get("/")
async def root():
    return {"status": "Mata Angel Aktif di Vercel"}

@web_app.get("/api/index")
async def check():
    return {"status": "Mata Angel Aktif di Vercel"}

# INI YANG DICARI VERCEL - JANGAN DIUBAH NAMANYA
app = web_app
