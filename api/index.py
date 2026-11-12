from fastapi import FastAPI, Request
from telegram import Update as TgUpdate
from telegram.ext import Application, CommandHandler, ChatMemberHandler, MessageHandler, ContextTypes, filters
from datetime import datetime
import os
import asyncpg

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

_pool = None
_is_init = False

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    return _pool

async def db_exec(query, *args):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(query, *args)

async def db_fetch(query, *args):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)

async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS menfessangel_groups (
            chat_id BIGINT PRIMARY KEY, title TEXT,
            mata_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS menfessangel_users (
            id SERIAL PRIMARY KEY, chat_id BIGINT NOT NULL, user_id BIGINT NOT NULL,
            name TEXT, username TEXT, updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(chat_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS menfessangel_messages (
            id SERIAL PRIMARY KEY, chat_id BIGINT NOT NULL, message_id BIGINT NOT NULL,
            user_name TEXT, username TEXT, text TEXT, created_at TIMESTAMP DEFAULT NOW()
        );
        """)

async def ensure_group(chat_id, title=""):
    await db_exec("INSERT INTO menfessangel_groups (chat_id, title) VALUES ($1, $2) ON CONFLICT (chat_id) DO NOTHING", int(chat_id), title or "")

async def get_settings(chat_id):
    rows = await db_fetch("SELECT mata_active FROM menfessangel_groups WHERE chat_id=$1", int(chat_id))
    if not rows:
        return {"mata_active": True}
    return {"mata_active": rows[0]["mata_active"]}

async def is_admin(update, context):
    if update.effective_chat.type == "private":
        return True
    try:
        m = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        return m.status in ["creator", "administrator"]
    except:
        return False

# ================= COMMANDS - MATA ANGEL TEGAS FORMAL =================
async def start(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text(
            "👁️ MATA ANGEL\n"
            "Sistem Pengawasan Grup\n\n"
            "Selamat datang. Saya adalah Mata Angel, sistem yang bertugas mengawasi aktivitas grup secara otomatis.\n\n"
            "Fungsi Saya:\n"
            "1. Mendeteksi perubahan nama dan username anggota\n"
            "2. Mendeteksi anggota yang bergabung dan meninggalkan grup\n"
            "3. Mencatat aktivitas anggota untuk keperluan laporan\n\n"
            "Cara Pemasangan:\n"
            "Undang saya ke grup Anda, jadikan Admin, kemudian kirim perintah /start di grup tersebut.\n\n"
            "Seluruh aktivitas akan dicatat dan tidak dapat disembunyikan."
        )
    else:
        await ensure_group(chat.id, chat.title)
        await update.message.reply_text(
            f"👁️ MATA ANGEL AKTIF\n\n"
            f"Grup: {chat.title}\n"
            f"ID Grup: `{chat.id}`\n"
            f"Status: Aktif dan Mengawasi\n\n"
            f"Mulai saat ini, seluruh aktivitas di grup ini berada dalam pengawasan.\n"
            f"Gunakan perintah /laporan untuk melihat hasil pengawasan."
        )

async def laporan(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Mohon maaf. Perintah ini hanya dapat diakses oleh Admin grup.")
        return
    chat_id = int(update.effective_chat.id)
    await ensure_group(chat_id, update.effective_chat.title)
    users = await db_fetch("SELECT COUNT(*) as c FROM menfessangel_users WHERE chat_id=$1", chat_id)
    msgs = await db_fetch("SELECT COUNT(*) as c FROM menfessangel_messages WHERE chat_id=$1", chat_id)
    s = await get_settings(chat_id)
    await update.message.reply_text(
        f"👁️ LAPORAN PENGAWASAN MATA ANGEL\n\n"
        f"ID Grup: `{chat_id}`\n"
        f"Anggota Terpantau: {users[0]['c']} orang\n"
        f"Pesan Tercatat: {msgs[0]['c']} pesan\n\n"
        f"Status Pengawasan: {'AKTIF' if s['mata_active'] else 'NONAKTIF'}\n"
        f"Waktu Laporan: {datetime.now().strftime('%d %B %Y - %H:%M WIB')}\n\n"
        f"Pengawasan berjalan sesuai ketentuan."
    )

async def mata_on(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    chat_id = int(update.effective_chat.id)
    await ensure_group(chat_id)
    await db_exec("UPDATE menfessangel_groups SET mata_active=TRUE WHERE chat_id=$1", chat_id)
    await update.message.reply_text("👁️ Pengawasan Mata Angel telah DIAKTIFKAN.\nMulai saat ini, seluruh aktivitas grup akan kembali dipantau.")

async def mata_off(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    chat_id = int(update.effective_chat.id)
    await ensure_group(chat_id)
    await db_exec("UPDATE menfessangel_groups SET mata_active=FALSE WHERE chat_id=$1", chat_id)
    await update.message.reply_text("👁️ Pengawasan Mata Angel telah DINONAKTIFKAN.\nUntuk mengaktifkan kembali, gunakan perintah /mata_on.")

async def id_grup(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 ID Grup ini adalah:\n`{update.effective_chat.id}`\n\nSilakan simpan ID tersebut untuk keperluan administrasi.")

# ================= TRACK MEMBER - TEGAS FORMAL =================
async def track_member(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    if not update.chat_member:
        return
    result = update.chat_member
    user = result.new_chat_member.user
    if user.is_bot:
        return
    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status
    waktu = datetime.now().strftime("%d %B %Y - %H:%M WIB")
    chat_id = int(update.effective_chat.id)

    await ensure_group(chat_id, update.effective_chat.title)
    s = await get_settings(chat_id)
    if not s["mata_active"]:
        return

    rows = await db_fetch("SELECT name, username FROM menfessangel_users WHERE chat_id=$1 AND user_id=$2", chat_id, user.id)
    old = rows[0] if rows else None

    if old and (old["name"] != user.full_name or old["username"] != user.username):
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"👁️ MATA ANGEL MENDETEKSI PERUBAHAN IDENTITAS\n\n"
                 f"Data Sebelumnya:\n"
                 f"Nama: {old['name']}\n"
                 f"Username: @{old['username']}\n\n"
                 f"Data Saat Ini:\n"
                 f"Nama: {user.full_name}\n"
                 f"Username: @{user.username}\n\n"
                 f"Perubahan ini telah dicatat dalam sistem.\n"
                 f"Waktu: {waktu}"
        )

    await db_exec(
        "INSERT INTO menfessangel_users (chat_id, user_id, name, username) VALUES ($1,$2,$3,$4) "
        "ON CONFLICT (chat_id, user_id) DO UPDATE SET name=$3, username=$4, updated_at=NOW()",
        chat_id, user.id, user.full_name, user.username
    )

    if old_status in ["left", "kicked"] and new_status in ["member", "administrator"]:
        await context.bot.send_message(chat_id=chat_id, text=f"👁️ MATA ANGEL\n\nAnggota Baru Bergabung\n\nNama: {user.full_name}\nUsername: @{user.username}\nWaktu: {waktu}\n\nSelamat datang. Harap mematuhi peraturan grup yang berlaku.")
    elif new_status in ["left", "kicked"]:
        await context.bot.send_message(chat_id=chat_id, text=f"👁️ MATA ANGEL\n\nAnggota Meninggalkan Grup\n\nNama: {user.full_name}\nUsername: @{user.username}\nWaktu: {waktu}\n\nKepergian anggota telah dicatat dalam sistem.")

async def save_message(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return
    if msg.from_user.is_bot:
        return
    chat_id = int(update.effective_chat.id)
    if chat_id == msg.from_user.id:
        return
    await ensure_group(chat_id, update.effective_chat.title)
    s = await get_settings(chat_id)
    if not s["mata_active"]:
        return

    await db_exec(
        "INSERT INTO menfessangel_messages (chat_id, message_id, user_name, username, text) VALUES ($1,$2,$3,$4,$5)",
        chat_id, msg.message_id, msg.from_user.full_name, msg.from_user.username, msg.text
    )
    rows = await db_fetch("SELECT name, username FROM menfessangel_users WHERE chat_id=$1 AND user_id=$2", chat_id, msg.from_user.id)
    old = rows[0] if rows else None
    if old and (old["name"] != msg.from_user.full_name or old["username"] != msg.from_user.username):
        await context.bot.send_message(chat_id=chat_id, text=f"👁️ MATA ANGEL MENDETEKSI PERUBAHAN IDENTITAS\n\nData Sebelumnya:\nNama: {old['name']}\nUsername: @{old['username']}\n\nData Saat Ini:\nNama: {msg.from_user.full_name}\nUsername: @{msg.from_user.username}\n\nPerubahan ini telah dicatat dalam sistem.")
    await db_exec(
        "INSERT INTO menfessangel_users (chat_id, user_id, name, username) VALUES ($1,$2,$3,$4) "
        "ON CONFLICT (chat_id, user_id) DO UPDATE SET name=$3, username=$4, updated_at=NOW()",
        chat_id, msg.from_user.id, msg.from_user.full_name, msg.from_user.username
    )

# ================= SETUP =================
ptb_app = Application.builder().token(BOT_TOKEN).build()
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CommandHandler("laporan", laporan))
ptb_app.add_handler(CommandHandler("mata_on", mata_on))
ptb_app.add_handler(CommandHandler("mata_off", mata_off))
ptb_app.add_handler(CommandHandler("idgrup", id_grup))
ptb_app.add_handler(ChatMemberHandler(track_member, ChatMemberHandler.CHAT_MEMBER))
ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_message))

web_app = FastAPI()

@web_app.post("/api/index")
async def webhook(request: Request):
    global _is_init
    if not _is_init:
        await ptb_app.initialize()
        await init_db()
        _is_init = True
    data = await request.json()
    update = TgUpdate.de_json(data, ptb_app.bot)
    await ptb_app.process_update(update)
    return {"ok": True}

@web_app.get("/")
async def root():
    return {"status": "Mata Angel Aktif", "db": "Neon menfessangel"}

@web_app.get("/api/index")
async def check():
    return {"status": "Mata Angel Aktif", "db": "Neon menfessangel"}

app = web_app
