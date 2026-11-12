from fastapi import FastAPI, Request
from telegram import Update as TgUpdate, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ChatMemberHandler, MessageHandler, ContextTypes, filters
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

# ================= KEYBOARD - TAB ADMIN =================
# Tab bar persis kayak SangMata: 4 tab di atas, isi di bawahnya ganti-ganti
def admin_tabs_kb(active_tab="overview", mata_active=True):
    def tab_label(name, key):
        return f"● {name}" if active_tab == key else name
    status_txt = "AKTIF" if mata_active else "NONAKTIF"
    kb = [
        # BAR TAB
        [InlineKeyboardButton(tab_label("Ringkasan", "overview"), callback_data="admin_tab_overview"),
         InlineKeyboardButton(tab_label("Anggota", "anggota"), callback_data="admin_tab_anggota"),
         InlineKeyboardButton(tab_label("Laporan", "laporan"), callback_data="admin_tab_laporan"),
         InlineKeyboardButton(tab_label("Pengaturan", "pengaturan"), callback_data="admin_tab_pengaturan")],
    ]
    # ISI PER TAB
    if active_tab == "overview":
        kb += [
            [InlineKeyboardButton(f"Status Pengawasan: {status_txt}", callback_data="admin_tab_pengaturan")],
            [InlineKeyboardButton("Lihat Laporan Lengkap", callback_data="admin_tab_laporan")],
        ]
    elif active_tab == "anggota":
        kb += [
            [InlineKeyboardButton("5 Anggota Terakhir Bergabung", callback_data="admin_list_join")],
            [InlineKeyboardButton("5 Perubahan Nama Terakhir", callback_data="admin_list_nama")],
            [InlineKeyboardButton("Semua Anggota Terpantau", callback_data="admin_list_all")],
        ]
    elif active_tab == "laporan":
        kb += [
            [InlineKeyboardButton("Laporan Hari Ini", callback_data="admin_laporan_hari")],
            [InlineKeyboardButton("Laporan Lengkap", callback_data="admin_laporan_full")],
        ]
    elif active_tab == "pengaturan":
        if mata_active:
            kb += [[InlineKeyboardButton("Nonaktifkan Pengawasan", callback_data="mata_off")]]
        else:
            kb += [[InlineKeyboardButton("Aktifkan Pengawasan", callback_data="mata_on")]]
        kb += [
            [InlineKeyboardButton("ID Grup", callback_data="menu_idgrup")],
            [InlineKeyboardButton("Bantuan", callback_data="menu_help")],
        ]
    kb += [[InlineKeyboardButton("Tutup Panel", callback_data="admin_close")]]
    return InlineKeyboardMarkup(kb)

def main_menu_kb(mata_active=True):
    status_btn = "Mata Pengawasan: AKTIF" if mata_active else "Mata Pengawasan: NONAKTIF"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Panel Admin", callback_data="admin_tab_overview")],
        [InlineKeyboardButton("Laporan Pengawasan", callback_data="menu_laporan"),
         InlineKeyboardButton("ID Grup", callback_data="menu_idgrup")],
        [InlineKeyboardButton(status_btn, callback_data="menu_status")],
        [InlineKeyboardButton("Aktifkan Pengawasan", callback_data="mata_on"),
         InlineKeyboardButton("Nonaktifkan Pengawasan", callback_data="mata_off")],
        [InlineKeyboardButton("Bantuan", callback_data="menu_help")],
    ])

def back_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Kembali ke Menu Utama", callback_data="menu_back")],
        [InlineKeyboardButton("Panel Admin", callback_data="admin_tab_overview")],
    ])

def laporan_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Kembali ke Menu Utama", callback_data="menu_back")],
        [InlineKeyboardButton("Panel Admin", callback_data="admin_tab_overview")],
    ])

def detect_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Lihat Laporan", callback_data="menu_laporan"),
         InlineKeyboardButton("Panel Admin", callback_data="admin_tab_overview")],
    ])

# ================= HELPERS - TEKS PER TAB =================
async def get_overview_text(chat_id, title):
    users = await db_fetch("SELECT COUNT(*) as c FROM menfessangel_users WHERE chat_id=$1", chat_id)
    msgs = await db_fetch("SELECT COUNT(*) as c FROM menfessangel_messages WHERE chat_id=$1", chat_id)
    recent = await db_fetch("SELECT name, username, updated_at FROM menfessangel_users WHERE chat_id=$1 ORDER BY updated_at DESC LIMIT 3", chat_id)
    s = await get_settings(chat_id)
    recent_txt = ""
    if recent:
        for i, u in enumerate(recent, 1):
            recent_txt += f"{i}. {u['name']} (@{u['username']})\n"
    else:
        recent_txt = "Belum ada data anggota.\n"
    return (
        f"PANEL ADMIN - RINGKASAN\n\n"
        f"Nama Grup: {title}\n"
        f"ID Grup: {chat_id}\n"
        f"Status Pengawasan: {'AKTIF' if s['mata_active'] else 'NONAKTIF'}\n\n"
        f"Jumlah Anggota Terpantau: {users[0]['c']} orang\n"
        f"Jumlah Pesan Tercatat: {msgs[0]['c']} pesan\n\n"
        f"Aktivitas Terakhir:\n{recent_txt}\n"
        f"Silakan pilih tab di atas untuk mengelola grup."
    )

async def get_anggota_text(chat_id, title):
    total = await db_fetch("SELECT COUNT(*) as c FROM menfessangel_users WHERE chat_id=$1", chat_id)
    recent = await db_fetch("SELECT name, username, updated_at FROM menfessangel_users WHERE chat_id=$1 ORDER BY updated_at DESC LIMIT 10", chat_id)
    txt = f"PANEL ADMIN - DATA ANGGOTA\n\nNama Grup: {title}\nTotal Anggota Terpantau: {total[0]['c']} orang\n\n10 Anggota Terakhir Terpantau:\n"
    if not recent:
        txt += "Belum ada data anggota."
    else:
        for i, u in enumerate(recent, 1):
            tgl = u['updated_at'].strftime("%d/%m %H:%M") if u['updated_at'] else "-"
            txt += f"{i}. {u['name']} (@{u['username']}) - {tgl}\n"
    return txt

async def get_laporan_text(chat_id, title=""):
    users = await db_fetch("SELECT COUNT(*) as c FROM menfessangel_users WHERE chat_id=$1", chat_id)
    msgs = await db_fetch("SELECT COUNT(*) as c FROM menfessangel_messages WHERE chat_id=$1", chat_id)
    s = await get_settings(chat_id)
    return (
        f"MATA ANGEL - LAPORAN PENGAWASAN\n\n"
        f"Nama Grup: {title}\n"
        f"ID Grup: {chat_id}\n"
        f"Jumlah Anggota Terpantau: {users[0]['c']} orang\n"
        f"Jumlah Pesan Tercatat: {msgs[0]['c']} pesan\n\n"
        f"Status Pengawasan: {'AKTIF' if s['mata_active'] else 'NONAKTIF'}\n"
        f"Waktu Laporan: {datetime.now().strftime('%d %B %Y - %H:%M WIB')}\n\n"
        f"Pengawasan dilaksanakan sesuai dengan ketentuan yang berlaku."
    )

async def get_pengaturan_text(chat_id, title):
    s = await get_settings(chat_id)
    return (
        f"PANEL ADMIN - PENGATURAN\n\n"
        f"Nama Grup: {title}\n"
        f"ID Grup: {chat_id}\n\n"
        f"Status Pengawasan Saat Ini: {'AKTIF' if s['mata_active'] else 'NONAKTIF'}\n\n"
        f"Pengaturan yang tersedia:\n"
        f"1. Aktifkan / Nonaktifkan Pengawasan\n"
        f"2. Melihat ID Grup\n"
        f"3. Bantuan Penggunaan\n\n"
        f"Silakan gunakan tombol di bawah ini untuk mengubah pengaturan."
    )

# ================= COMMANDS =================
async def start(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    bot_username = context.bot.username or "MataAngelBot"
    if chat.type == "private":
        await update.message.reply_text(
            "Selamat Datang di Mata Angel\n\n"
            "Mata Angel merupakan sistem pengawasan grup yang berfungsi untuk memantau aktivitas anggota secara otomatis dan akurat.\n\n"
            "Bagi Pengelola Grup:\n"
            "Anda dapat menambahkan bot ini ke grup Anda melalui tombol di bawah ini. "
            "Pastikan Mata Angel ditambahkan sebagai Administrator dengan izin Kelola Grup agar seluruh fitur dapat berfungsi secara optimal.\n\n"
            "Layanan Penelusuran Riwayat Pengguna:\n"
            "Terdapat 3 (tiga) cara untuk melakukan penelusuran riwayat pengguna, yaitu:\n"
            "1. Meneruskan pesan pengguna yang bersangkutan ke obrolan ini.\n"
            "2. Mengirimkan ID atau nama pengguna yang bersangkutan ke obrolan ini.\n"
            "3. Menggunakan perintah \"history\" atau \"allhistory\". Silakan kirim \"help\" untuk informasi lebih lanjut.\n\n"
            "Bantuan:\n"
            "Apabila Anda memerlukan bantuan lebih lanjut, silakan kirim pesan \"help\" pada obrolan ini.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Tambahkan Mata Angel ke Grup Saya", url=f"https://t.me/{bot_username}?startgroup=true")],
            ])
        )
    else:
        await ensure_group(chat.id, chat.title)
        s = await get_settings(chat.id)
        # Kalau yang /start admin, langsung kasih Panel Admin, kalau member biasa kasih menu biasa
        if await is_admin(update, context):
            await update.message.reply_text(
                f"MATA ANGEL TELAH DIAKTIFKAN\n\n"
                f"Nama Grup: {chat.title}\n"
                f"Status Pengawasan: {'AKTIF' if s['mata_active'] else 'NONAKTIF'}\n\n"
                f"Panel Admin khusus telah dibuka untuk Anda. Silakan gunakan tab di atas untuk mengelola grup.",
                reply_markup=admin_tabs_kb("overview", s['mata_active'])
            )
        else:
            await update.message.reply_text(
                f"MATA ANGEL TELAH DIAKTIFKAN\n\n"
                f"Nama Grup: {chat.title}\n"
                f"Status Pengawasan: {'AKTIF' if s['mata_active'] else 'NONAKTIF'}\n\n"
                f"Mulai saat ini, seluruh aktivitas pada grup ini berada dalam pengawasan Mata Angel.",
                reply_markup=main_menu_kb(s['mata_active'])
            )

async def admin_cmd(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text("Panel Admin hanya dapat diakses di dalam grup.")
        return
    if not await is_admin(update, context):
        await update.message.reply_text("Mohon maaf. Panel Admin hanya dapat diakses oleh Administrator grup.")
        return
    await ensure_group(chat.id, chat.title)
    s = await get_settings(chat.id)
    text = await get_overview_text(int(chat.id), chat.title)
    await update.message.reply_text(text, reply_markup=admin_tabs_kb("overview", s['mata_active']))

async def menu_cmd(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == "private":
        bot_username = context.bot.username or "MataAngelBot"
        await update.message.reply_text(
            "MENU UTAMA MATA ANGEL\n\n"
            "Anda saat ini berada pada obrolan pribadi.\n"
            "Untuk memulai pengawasan, silakan tambahkan Mata Angel ke grup Anda terlebih dahulu.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Tambahkan Mata Angel ke Grup Saya", url=f"https://t.me/{bot_username}?startgroup=true")],
            ])
        )
        return
    await ensure_group(chat.id, chat.title)
    s = await get_settings(chat.id)
    await update.message.reply_text(
        f"MENU UTAMA MATA ANGEL\n\n"
        f"Nama Grup: {chat.title}\n"
        f"Status Pengawasan: {'AKTIF' if s['mata_active'] else 'NONAKTIF'}\n\n"
        f"Silakan pilih menu yang tersedia di bawah ini.",
        reply_markup=main_menu_kb(s['mata_active'])
    )

async def laporan(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Mohon maaf. Perintah ini hanya dapat diakses oleh Administrator grup.")
        return
    chat_id = int(update.effective_chat.id)
    await ensure_group(chat_id, update.effective_chat.title)
    text = await get_laporan_text(chat_id, update.effective_chat.title)
    await update.message.reply_text(text, reply_markup=laporan_kb())

async def mata_on(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    chat_id = int(update.effective_chat.id)
    await ensure_group(chat_id)
    await db_exec("UPDATE menfessangel_groups SET mata_active=TRUE WHERE chat_id=$1", chat_id)
    await update.message.reply_text("Pengawasan Mata Angel telah diaktifkan. Seluruh aktivitas grup akan kembali dipantau.", reply_markup=back_menu_kb())

async def mata_off(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    chat_id = int(update.effective_chat.id)
    await ensure_group(chat_id)
    await db_exec("UPDATE menfessangel_groups SET mata_active=FALSE WHERE chat_id=$1", chat_id)
    await update.message.reply_text("Pengawasan Mata Angel telah dinonaktifkan.", reply_markup=back_menu_kb())

async def id_grup(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"INFORMASI ID GRUP\n\nID Grup ini adalah:\n{update.effective_chat.id}\n\nMohon simpan ID tersebut untuk keperluan administrasi grup.",
        reply_markup=back_menu_kb()
    )

async def help_cmd(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    bot_username = context.bot.username or "MataAngelBot"
    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "PANDUAN PENGGUNAAN MATA ANGEL\n\n"
            "Tata Cara Pemasangan:\n"
            "1. Tekan tombol Tambahkan Mata Angel ke Grup Saya di bawah ini.\n"
            "2. Pilih grup yang akan diawasi.\n"
            "3. Tetapkan Mata Angel sebagai Administrator dengan izin Kelola Grup.\n"
            "4. Kirim perintah /start pada grup tersebut.\n\n"
            "Daftar Perintah pada Grup:\n"
            "/start - Menu utama\n"
            "/menu - Menu pengawasan\n"
            "/admin - Panel Admin khusus\n"
            "/laporan - Laporan pengawasan\n"
            "/mata_on - Mengaktifkan pengawasan\n"
            "/mata_off - Menonaktifkan pengawasan\n"
            "/idgrup - Menampilkan ID grup",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Tambahkan Mata Angel ke Grup Saya", url=f"https://t.me/{bot_username}?startgroup=true")],
                [InlineKeyboardButton("Kembali ke Menu Utama", callback_data="menu_back")],
            ])
        )
        return
    await update.message.reply_text(
        "PANDUAN PENGGUNAAN MATA ANGEL\n\n"
        "Daftar Perintah yang Tersedia:\n"
        "/start - Menu utama\n"
        "/menu - Menu pengawasan\n"
        "/admin - Panel Admin khusus\n"
        "/laporan - Laporan pengawasan\n"
        "/mata_on - Mengaktifkan pengawasan\n"
        "/mata_off - Menonaktifkan pengawasan\n"
        "/idgrup - ID grup\n\n"
        "Seluruh perintah tersebut juga dapat diakses melalui tombol yang tersedia.",
        reply_markup=back_menu_kb()
    )

# ================= CALLBACK - TAB ADMIN + MENU =================
async def button_handler(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat = update.effective_chat
    chat_id = int(chat.id)
    data = query.data
    bot_username = context.bot.username or "MataAngelBot"

    # Semua tab admin + laporan + on/off hanya untuk admin di grup
    if data.startswith("admin_") or data in ["menu_laporan", "mata_on", "mata_off"]:
        if chat.type != "private" and not await is_admin(update, context):
            await query.answer("Panel ini hanya dapat diakses oleh Administrator.", show_alert=True)
            return

    s = await get_settings(chat_id)

    # --- TAB ADMIN ---
    if data == "admin_tab_overview":
        text = await get_overview_text(chat_id, chat.title)
        await query.edit_message_text(text, reply_markup=admin_tabs_kb("overview", s['mata_active']))
    elif data == "admin_tab_anggota":
        text = await get_anggota_text(chat_id, chat.title)
        await query.edit_message_text(text, reply_markup=admin_tabs_kb("anggota", s['mata_active']))
    elif data == "admin_tab_laporan":
        text = await get_laporan_text(chat_id, chat.title)
        await query.edit_message_text(text, reply_markup=admin_tabs_kb("laporan", s['mata_active']))
    elif data == "admin_tab_pengaturan":
        text = await get_pengaturan_text(chat_id, chat.title)
        await query.edit_message_text(text, reply_markup=admin_tabs_kb("pengaturan", s['mata_active']))
    elif data == "admin_list_join":
        rows = await db_fetch("SELECT name, username, updated_at FROM menfessangel_users WHERE chat_id=$1 ORDER BY updated_at DESC LIMIT 5", chat_id)
        txt = "PANEL ADMIN - 5 ANGGOTA TERAKHIR BERGABUNG\n\n"
        if not rows:
            txt += "Belum ada data anggota."
        else:
            for i, u in enumerate(rows, 1):
                tgl = u['updated_at'].strftime("%d %B %Y %H:%M") if u['updated_at'] else "-"
                txt += f"{i}. {u['name']} (@{u['username']})\n   Terpantau: {tgl}\n"
        await query.edit_message_text(txt, reply_markup=admin_tabs_kb("anggota", s['mata_active']))
    elif data == "admin_list_nama":
        rows = await db_fetch("SELECT name, username, updated_at FROM menfessangel_users WHERE chat_id=$1 ORDER BY updated_at DESC LIMIT 5", chat_id)
        txt = "PANEL ADMIN - 5 PERUBAHAN NAMA TERAKHIR\n\n"
        if not rows:
            txt += "Belum ada perubahan nama yang tercatat."
        else:
            for i, u in enumerate(rows, 1):
                txt += f"{i}. {u['name']} (@{u['username']})\n"
        txt += "\nCatatan: Perubahan nama terdeteksi secara otomatis saat anggota mengirim pesan atau memperbarui profil."
        await query.edit_message_text(txt, reply_markup=admin_tabs_kb("anggota", s['mata_active']))
    elif data == "admin_list_all":
        total = await db_fetch("SELECT COUNT(*) as c FROM menfessangel_users WHERE chat_id=$1", chat_id)
        txt = f"PANEL ADMIN - SEMUA ANGGOTA TERPANTAU\n\nTotal: {total[0]['c']} orang\n\nGunakan menu Anggota untuk melihat 10 anggota terakhir secara detail."
        await query.edit_message_text(txt, reply_markup=admin_tabs_kb("anggota", s['mata_active']))
    elif data == "admin_laporan_hari":
        msgs = await db_fetch("SELECT COUNT(*) as c FROM menfessangel_messages WHERE chat_id=$1 AND created_at >= NOW() - INTERVAL '1 day'", chat_id)
        txt = f"PANEL ADMIN - LAPORAN HARI INI\n\nNama Grup: {chat.title}\nPesan Tercatat 24 Jam Terakhir: {msgs[0]['c']} pesan\nWaktu: {datetime.now().strftime('%d %B %Y - %H:%M WIB')}"
        await query.edit_message_text(txt, reply_markup=admin_tabs_kb("laporan", s['mata_active']))
    elif data == "admin_laporan_full":
        text = await get_laporan_text(chat_id, chat.title)
        await query.edit_message_text(text, reply_markup=admin_tabs_kb("laporan", s['mata_active']))
    elif data == "admin_close":
        await query.edit_message_text("Panel Admin telah ditutup. Untuk membuka kembali, silakan kirim perintah /admin pada grup ini.")
    # --- MENU BIASA ---
    elif data == "menu_laporan":
        await ensure_group(chat_id, chat.title)
        text = await get_laporan_text(chat_id, chat.title)
        await query.edit_message_text(text, reply_markup=laporan_kb())
    elif data == "menu_idgrup":
        await query.edit_message_text(f"INFORMASI ID GRUP\n\nID Grup ini adalah:\n{chat_id}\n\nMohon simpan ID tersebut untuk keperluan administrasi grup.", reply_markup=back_menu_kb())
    elif data == "menu_status":
        await query.edit_message_text(f"STATUS PENGAWASAN MATA ANGEL\n\nNama Grup: {chat.title}\nStatus: {'AKTIF - Pengawasan sedang berlangsung' if s['mata_active'] else 'NONAKTIF - Pengawasan dihentikan sementara'}\nWaktu Pemeriksaan: {datetime.now().strftime('%d %B %Y - %H:%M WIB')}", reply_markup=main_menu_kb(s['mata_active']))
    elif data == "mata_on":
        await ensure_group(chat_id, chat.title)
        await db_exec("UPDATE menfessangel_groups SET mata_active=TRUE WHERE chat_id=$1", chat_id)
        await query.edit_message_text("Pengawasan Mata Angel telah diaktifkan. Mulai saat ini, seluruh aktivitas grup akan kembali dipantau.", reply_markup=admin_tabs_kb("pengaturan", True))
    elif data == "mata_off":
        await ensure_group(chat_id, chat.title)
        await db_exec("UPDATE menfessangel_groups SET mata_active=FALSE WHERE chat_id=$1", chat_id)
        await query.edit_message_text("Pengawasan Mata Angel telah dinonaktifkan. Untuk mengaktifkan kembali, silakan tekan tombol yang tersedia di bawah ini.", reply_markup=admin_tabs_kb("pengaturan", False))
    elif data == "menu_help":
        if chat.type == "private":
            await query.edit_message_text("PANDUAN PENGGUNAAN MATA ANGEL\n\nTata Cara Pemasangan:\n1. Tekan tombol Tambahkan Mata Angel ke Grup Saya.\n2. Pilih grup yang akan diawasi.\n3. Tetapkan Mata Angel sebagai Administrator.\n4. Kirim perintah /start pada grup tersebut.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Tambahkan Mata Angel ke Grup Saya", url=f"https://t.me/{bot_username}?startgroup=true")],[InlineKeyboardButton("Kembali ke Menu Utama", callback_data="menu_back")]]))
        else:
            await query.edit_message_text("PANDUAN PENGGUNAAN MATA ANGEL\n\nDaftar Perintah:\n/start - Menu utama\n/menu - Menu pengawasan\n/admin - Panel Admin khusus\n/laporan - Laporan pengawasan\n/mata_on - Mengaktifkan pengawasan\n/mata_off - Menonaktifkan pengawasan\n/idgrup - ID grup", reply_markup=back_menu_kb())
    elif data == "menu_back":
        if chat.type == "private":
            await query.edit_message_text("Selamat Datang di Mata Angel\n\nMata Angel merupakan sistem pengawasan grup yang berfungsi untuk memantau aktivitas anggota secara otomatis.\n\nBagi Pengelola Grup:\nAnda dapat menambahkan bot ini ke grup Anda melalui tombol di bawah ini. Pastikan Mata Angel ditambahkan sebagai Administrator dengan izin Kelola Grup agar seluruh fitur dapat berfungsi secara optimal.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Tambahkan Mata Angel ke Grup Saya", url=f"https://t.me/{bot_username}?startgroup=true")]]))
            return
        await ensure_group(chat_id, chat.title)
        s2 = await get_settings(chat_id)
        await query.edit_message_text(f"MENU UTAMA MATA ANGEL\n\nNama Grup: {chat.title}\nStatus Pengawasan: {'AKTIF' if s2['mata_active'] else 'NONAKTIF'}\n\nSilakan pilih menu yang tersedia di bawah ini.", reply_markup=main_menu_kb(s2['mata_active']))

# ================= TRACK MEMBER =================
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
        await context.bot.send_message(chat_id=chat_id, text=f"MATA ANGEL - DETEKSI PERUBAHAN IDENTITAS\n\nData Sebelumnya:\nNama: {old['name']}\nNama Pengguna: @{old['username']}\n\nData Saat Ini:\nNama: {user.full_name}\nNama Pengguna: @{user.username}\n\nPerubahan tersebut telah dicatat dalam sistem pengawasan.\nWaktu Deteksi: {waktu}", reply_markup=detect_kb())
    await db_exec("INSERT INTO menfessangel_users (chat_id, user_id, name, username) VALUES ($1,$2,$3,$4) ON CONFLICT (chat_id, user_id) DO UPDATE SET name=$3, username=$4, updated_at=NOW()", chat_id, user.id, user.full_name, user.username)
    if old_status in ["left", "kicked"] and new_status in ["member", "administrator"]:
        await context.bot.send_message(chat_id=chat_id, text=f"MATA ANGEL - ANGGOTA BARU BERGABUNG\n\nNama: {user.full_name}\nNama Pengguna: @{user.username}\nWaktu: {waktu}\n\nSelamat datang. Diharapkan untuk mematuhi peraturan grup yang berlaku.", reply_markup=detect_kb())
    elif new_status in ["left", "kicked"]:
        await context.bot.send_message(chat_id=chat_id, text=f"MATA ANGEL - ANGGOTA MENINGGALKAN GRUP\n\nNama: {user.full_name}\nNama Pengguna: @{user.username}\nWaktu: {waktu}\n\nKepergian anggota tersebut telah dicatat dalam sistem pengawasan.", reply_markup=detect_kb())

async def track_join_leave_msg(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    chat_id = int(update.effective_chat.id)
    await ensure_group(chat_id, update.effective_chat.title)

    # === BOT BARU DI-ADD KE GRUP -> LANGSUNG KIRIM PANEL ADMIN ===
    if msg.new_chat_members:
        for u in msg.new_chat_members:
            if u.id == context.bot.id:
                s = await get_settings(chat_id)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"MATA ANGEL TELAH DITAMBAHKAN KE GRUP INI\n\n"
                         f"Nama Grup: {update.effective_chat.title}\n"
                         f"Status Pengawasan: {'AKTIF' if s['mata_active'] else 'NONAKTIF'}\n\n"
                         f"Kepada Administrator grup, silakan tetapkan Mata Angel sebagai Administrator dengan izin Kelola Grup agar seluruh fitur dapat berfungsi secara optimal.\n\n"
                         f"Panel Admin khusus telah dibuka di bawah ini. Panel ini hanya dapat diakses oleh Administrator.",
                    reply_markup=admin_tabs_kb("overview", s['mata_active'])
                )
                continue
            if u.is_bot:
                continue
            s = await get_settings(chat_id)
            if not s["mata_active"]:
                continue
            waktu = datetime.now().strftime("%d %B %Y - %H:%M WIB")
            await db_exec("INSERT INTO menfessangel_users (chat_id, user_id, name, username) VALUES ($1,$2,$3,$4) ON CONFLICT (chat_id, user_id) DO UPDATE SET name=$3, username=$4, updated_at=NOW()", chat_id, u.id, u.full_name, u.username)
            await context.bot.send_message(chat_id=chat_id, text=f"MATA ANGEL - ANGGOTA BARU BERGABUNG\n\nNama: {u.full_name}\nNama Pengguna: @{u.username}\nWaktu: {waktu}\n\nSelamat datang. Diharapkan untuk mematuhi peraturan grup yang berlaku.", reply_markup=detect_kb())
    if msg.left_chat_member:
        user = msg.left_chat_member
        if not user.is_bot:
            s = await get_settings(chat_id)
            if not s["mata_active"]:
                return
            waktu = datetime.now().strftime("%d %B %Y - %H:%M WIB")
            await context.bot.send_message(chat_id=chat_id, text=f"MATA ANGEL - ANGGOTA MENINGGALKAN GRUP\n\nNama: {user.full_name}\nNama Pengguna: @{user.username}\nWaktu: {waktu}\n\nKepergian anggota tersebut telah dicatat dalam sistem pengawasan.", reply_markup=detect_kb())

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
    await db_exec("INSERT INTO menfessangel_messages (chat_id, message_id, user_name, username, text) VALUES ($1,$2,$3,$4,$5)", chat_id, msg.message_id, msg.from_user.full_name, msg.from_user.username, msg.text)
    rows = await db_fetch("SELECT name, username FROM menfessangel_users WHERE chat_id=$1 AND user_id=$2", chat_id, msg.from_user.id)
    old = rows[0] if rows else None
    if old and (old["name"] != msg.from_user.full_name or old["username"] != msg.from_user.username):
        await context.bot.send_message(chat_id=chat_id, text=f"MATA ANGEL - DETEKSI PERUBAHAN IDENTITAS\n\nData Sebelumnya:\nNama: {old['name']}\nNama Pengguna: @{old['username']}\n\nData Saat Ini:\nNama: {msg.from_user.full_name}\nNama Pengguna: @{msg.from_user.username}\n\nPerubahan tersebut telah dicatat dalam sistem pengawasan.", reply_markup=detect_kb())
    await db_exec("INSERT INTO menfessangel_users (chat_id, user_id, name, username) VALUES ($1,$2,$3,$4) ON CONFLICT (chat_id, user_id) DO UPDATE SET name=$3, username=$4, updated_at=NOW()", chat_id, msg.from_user.id, msg.from_user.full_name, msg.from_user.username)

# ================= SETUP =================
ptb_app = Application.builder().token(BOT_TOKEN).build()
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CommandHandler("menu", menu_cmd))
ptb_app.add_handler(CommandHandler("admin", admin_cmd))
ptb_app.add_handler(CommandHandler("panel", admin_cmd))
ptb_app.add_handler(CommandHandler("pengaturan", admin_cmd))
ptb_app.add_handler(CommandHandler("laporan", laporan))
ptb_app.add_handler(CommandHandler("mata_on", mata_on))
ptb_app.add_handler(CommandHandler("mata_off", mata_off))
ptb_app.add_handler(CommandHandler("idgrup", id_grup))
ptb_app.add_handler(CommandHandler("help", help_cmd))
ptb_app.add_handler(CommandHandler("bantuan", help_cmd))
ptb_app.add_handler(CallbackQueryHandler(button_handler))
ptb_app.add_handler(ChatMemberHandler(track_member, ChatMemberHandler.CHAT_MEMBER))
ptb_app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.StatusUpdate.LEFT_CHAT_MEMBER, track_join_leave_msg))
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
