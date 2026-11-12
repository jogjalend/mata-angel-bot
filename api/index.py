from fastapi import FastAPI, Request
from telegram import Update as TgUpdate
from telegram.ext import Application, CommandHandler, ChatMemberHandler, MessageHandler, ContextTypes, filters
from datetime import datetime
import os, random, string
import asyncpg

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

_pool = None

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

async def ensure_group(chat_id, title=""):
    await db_exec(
        "INSERT INTO menfessangel_groups (chat_id, title) VALUES ($1, $2) ON CONFLICT (chat_id) DO NOTHING",
        int(chat_id), title or ""
    )

async def get_settings(chat_id):
    rows = await db_fetch("SELECT mata_active, menfess_active FROM menfessangel_groups WHERE chat_id=$1", int(chat_id))
    if not rows:
        return {"mata_active": True, "menfess_active": True}
    return {"mata_active": rows[0]["mata_active"], "menfess_active": rows[0]["menfess_active"]}

def gen_kode():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# ================= COMMANDS =================
async def start(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text(
            "👁️ 𝗠𝗔𝗧𝗔 𝗔𝗡𝗚𝗘𝗟 x 𝗠𝗘𝗡𝗙𝗘𝗦𝗦𝗔𝗡𝗚𝗘𝗟\n\n"
            "DB: Neon - menfessangel (Shared)\n\n"
            "𝗠𝗘𝗡𝗙𝗘𝗦𝗦:\n"
            "`/menfess <id_grup> <pesan>`\n"
            "Contoh: `/menfess -100123456 Halo`\n\n"
            "𝗚𝗥𝗨𝗣:\n"
            "Invite saya ke grup, jadikan Admin.\n"
            "Perintah di grup: /laporan /mata_on /mata_off /idgrup"
        )
    else:
        await ensure_group(chat.id, chat.title)
        await update.message.reply_text(
            f"👁️ 𝗠𝗔𝗧𝗔 𝗔𝗡𝗚𝗘𝗟 𝗔𝗞𝗧𝗜𝗙\n\n"
            f"Grup: {chat.title}\n"
            f"ID Grup: `{chat.id}`\n"
            f"DB: Neon menfessangel\n\n"
            f"Perintah: /laporan /mata_on /mata_off /idgrup"
        )

async def laporan(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    chat_id = int(update.effective_chat.id)
    await ensure_group(chat_id, update.effective_chat.title)
    users = await db_fetch("SELECT COUNT(*) as c FROM menfessangel_users WHERE chat_id=$1", chat_id)
    msgs = await db_fetch("SELECT COUNT(*) as c FROM menfessangel_messages WHERE chat_id=$1", chat_id)
    menfess = await db_fetch("SELECT COUNT(*) as c FROM menfessangel_menfess WHERE target_chat_id=$1", chat_id)
    s = await get_settings(chat_id)
    await update.message.reply_text(
        f"👁️ 𝗟𝗔𝗣𝗢𝗥𝗔𝗡 𝗠𝗔𝗧𝗔 𝗔𝗡𝗚𝗘𝗟\n\n"
        f"ID Grup: `{chat_id}`\n"
        f"Member Terpantau: {users[0]['c']}\n"
        f"Pesan Tersimpan: {msgs[0]['c']}\n"
        f"Menfess Masuk: {menfess[0]['c']}\n"
        f"Status Mata: {'AKTIF ✅' if s['mata_active'] else 'NONAKTIF ❌'}\n"
        f"DB: Neon menfessangel\n"
        f"Waktu: {datetime.now().strftime('%d %B %Y - %H:%M WIB')}"
    )

async def mata_on(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    chat_id = int(update.effective_chat.id)
    await ensure_group(chat_id)
    await db_exec("UPDATE menfessangel_groups SET mata_active=TRUE WHERE chat_id=$1", chat_id)
    await update.message.reply_text("👁️ Mata Angel DIAKTIFKAN di grup ini.")

async def mata_off(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    chat_id = int(update.effective_chat.id)
    await ensure_group(chat_id)
    await db_exec("UPDATE menfessangel_groups SET mata_active=FALSE WHERE chat_id=$1", chat_id)
    await update.message.reply_text("👁️ Mata Angel DINONAKTIFKAN di grup ini.")

async def id_grup(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 ID Grup ini: `{update.effective_chat.id}`\nCopy untuk kirim menfess.")

async def menfess(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("💌 Cara: `/menfess <id_grup> <pesan>`\nContoh: `/menfess -100123456 Halo`")
        return
    target_id = context.args[0]
    pesan = " ".join(context.args[1:])
    kode = gen_kode()
    sender_id = update.effective_user.id
    try:
        await ensure_group(int(target_id))
        await db_exec(
            "INSERT INTO menfessangel_menfess (target_chat_id, kode, pesan, sender_id) VALUES ($1,$2,$3,$4)",
            int(target_id), kode, pesan, sender_id
        )
        await context.bot.send_message(
            chat_id=int(target_id),
            text=f"💌 𝗠𝗘𝗡𝗙𝗘𝗦𝗦𝗔𝗡𝗚𝗘𝗟 𝗠𝗔𝗦𝗨𝗞\n\n📩 {pesan}\n\n— Anonim\nKode: {kode}"
        )
        await update.message.reply_text(f"✅ Menfess terkirim! Kode: {kode}")
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal. Pastikan bot ada di grup tujuan.\nError: {e}")

# ================= TRACK MEMBER =================
async def track_member(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    user = result.new_chat_member.user
    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status
    waktu = datetime.now().strftime("%H:%M WIB")
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
            text=f"👁️ 𝗠𝗔𝗧𝗔 𝗔𝗡𝗚𝗘𝗟 𝗠𝗘𝗡𝗗𝗘𝗧𝗘𝗞𝗦𝗜\n\n👤 Sebelumnya: {old['name']} - @{old['username']}\n👤 Sekarang: {user.full_name} - @{user.username}\n🔄 Status: GANTI IDENTITAS\n🕐 Waktu: {waktu}"
        )

    await db_exec(
        "INSERT INTO menfessangel_users (chat_id, user_id, name, username) VALUES ($1,$2,$3,$4) "
        "ON CONFLICT (chat_id, user_id) DO UPDATE SET name=$3, username=$4, updated_at=NOW()",
        chat_id, user.id, user.full_name, user.username
    )

    if old_status in ["left", "kicked"] and new_status in ["member", "administrator"]:
        await context.bot.send_message(chat_id=chat_id, text=f"👁️ 𝗠𝗔𝗧𝗔 𝗔𝗡𝗚𝗘𝗟\n\n👤 {user.full_name}\n📥 BARU BERGABUNG\n🕐 {waktu}")
    elif new_status in ["left", "kicked"]:
        await context.bot.send_message(chat_id=chat_id, text=f"👁️ 𝗠𝗔𝗧𝗔 𝗔𝗡𝗚𝗘𝗟\n\n👤 {user.full_name}\n📤 MENINGGALKAN GRUP\n🕐 {waktu}")

async def save_message(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
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
        await context.bot.send_message(chat_id=chat_id, text=f"👁️ 𝗠𝗔𝗧𝗔 𝗔𝗡𝗚𝗘𝗟\n\n👤 Sebelumnya: {old['name']} - @{old['username']}\n👤 Sekarang: {msg.from_user.full_name} - @{msg.from_user.username}\n🔄 GANTI IDENTITAS")
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
ptb_app.add_handler(CommandHandler("menfess", menfess))
ptb_app.add_handler(ChatMemberHandler(track_member, ChatMemberHandler.CHAT_MEMBER))
ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_message))

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
    return {"status": "Mata Angel + MenfessAngel Aktif", "db": "Neon menfessangel"}

@web_app.get("/api/index")
async def check():
    return {"status": "Mata Angel + MenfessAngel Aktif", "db": "Neon menfessangel"}

app = web_app
