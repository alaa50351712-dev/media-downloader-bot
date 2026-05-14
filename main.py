import os
import logging
import yt_dlp
import asyncio
import sqlite3
from datetime import datetime
from collections import deque

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# =========================
# CONFIG
# =========================

TOKEN = "8073621434:AAH-Bm7fVfkl-1VeGZGE_oyBLGr2tSCNnhE"
ADMIN_ID = 1485891563

DOWNLOAD_PATH = "downloads"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================
# DATABASE
# =========================

conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    username TEXT,
    first_seen TEXT,
    last_seen TEXT,
    uses INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    url TEXT,
    type TEXT,
    time TEXT
)
""")

conn.commit()

# =========================
# QUEUE
# =========================

queue = deque()
processing = False

# =========================
# MEMORY
# =========================

user_mode = {}

# =========================
# TIME
# =========================

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# =========================
# USER SYSTEM
# =========================

def add_user(user):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user.id,))
    if not cursor.fetchone():
        cursor.execute("""
        INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)
        """, (user.id, user.first_name, user.username, now(), now(), 1))
    else:
        cursor.execute("""
        UPDATE users SET last_seen=?, uses=uses+1 WHERE user_id=?
        """, (now(), user.id))

    conn.commit()

def log_download(user_id, url, type_):
    cursor.execute("""
    INSERT INTO downloads (user_id, url, type, time)
    VALUES (?, ?, ?, ?)
    """, (user_id, url, type_, now()))
    conn.commit()

# =========================
# 🔥 SEND EVERY LINK TO ADMIN
# =========================

async def notify_admin_link(context, user, url, mode):
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "📥 رابط جديد وصل للبوت\n\n"
                f"👤 الاسم: {user.first_name}\n"
                f"🆔 ID: {user.id}\n"
                f"📌 النوع: {mode}\n"
                f"🔗 الرابط:\n{url}\n"
                f"⏰ الوقت: {now()}"
            )
        )
    except Exception as e:
        logger.error(f"Admin notify error: {e}")

# =========================
# WELCOME
# =========================

WELCOME_TEXT = """
🔥 مرحبًا بك في بوت التحميل الاحترافي 🔥

🎬 فيديوهات
🎵 صوت MP3
🖼 صور

📩 اختر النوع ثم أرسل الرابط
"""

# =========================
# KEYBOARD
# =========================

def get_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 تحميل فيديو", callback_data="video")],
        [InlineKeyboardButton("🎵 تحميل صوت", callback_data="audio")],
        [InlineKeyboardButton("🖼 تحميل صورة", callback_data="image")],
        [InlineKeyboardButton("👨‍💻 المطور", url="https://t.me/ALAA_ASC_74")]
    ])

# =========================
# ADMIN NOTIFY USER JOIN
# =========================

async def notify_admin(context, user):
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"""
👤 مستخدم جديد

الاسم: {user.first_name}
يوزر: @{user.username if user.username else 'None'}
ID: {user.id}
وقت: {now()}
"""
        )
    except:
        pass

# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    add_user(user)

    await notify_admin(context, user)

    await update.message.reply_text(
        WELCOME_TEXT,
        reply_markup=get_keyboard()
    )

# =========================
# BUTTONS
# =========================

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    user_mode[query.from_user.id] = query.data

    await query.edit_message_text(
        f"✅ تم اختيار: {query.data}\n\n📩 أرسل الرابط الآن"
    )

# =========================
# DOWNLOADS
# =========================

def download_video(url, path):
    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "outtmpl": path,
        "quiet": True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def download_audio(url, path):
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": path,
        "quiet": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192"
        }]
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

# =========================
# RUN SAFE
# =========================

async def run_blocking(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)

# =========================
# QUEUE PROCESSOR
# =========================

async def process_queue(app):

    global processing

    if processing:
        return

    processing = True

    while queue:

        job = queue.popleft()
        update = job["update"]
        context = job["context"]
        url = job["url"]
        mode = job["mode"]

        user = update.effective_user

        try:
            msg = await update.message.reply_text("⏳ جاري التحميل...")

            # 🔥 إرسال الرابط للأدمن فوراً
            await notify_admin_link(context, user, url, mode)

            if mode == "video":
                path = f"{DOWNLOAD_PATH}/{user.id}.mp4"
                await run_blocking(download_video, url, path)

                with open(path, "rb") as f:
                    await update.message.reply_video(video=f)

                os.remove(path)

            elif mode == "audio":
                path = f"{DOWNLOAD_PATH}/{user.id}"
                await run_blocking(download_audio, url, path)

                mp3 = path + ".mp3"
                with open(mp3, "rb") as f:
                    await update.message.reply_audio(audio=f)

                os.remove(mp3)

            elif mode == "image":
                await update.message.reply_photo(photo=url)

            log_download(user.id, url, mode)

            await msg.edit_text("✅ تم بنجاح")

        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: {e}")

    processing = False

# =========================
# MESSAGE HANDLER
# =========================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    url = update.message.text.strip()

    if not url.startswith("http"):
        await update.message.reply_text("❌ رابط غير صحيح")
        return

    mode = user_mode.get(user.id)

    if not mode:
        await update.message.reply_text("⚠️ اختر نوع التحميل أولاً")
        return

    add_user(user)

    queue.append({
        "update": update,
        "context": context,
        "url": url,
        "mode": mode
    })

    await update.message.reply_text("📥 تم إضافة الطلب في الطابور...")

    await process_queue(context.application)

# =========================
# ADMIN
# =========================

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM downloads")
    downloads_count = cursor.fetchone()[0]

    await update.message.reply_text(
        f"📊 لوحة التحكم\n\n"
        f"👥 المستخدمين: {users_count}\n"
        f"📥 التحميلات: {downloads_count}\n"
        f"⚡ الحالة: شغال"
    )

# =========================
# MAIN
# =========================

def main():

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🚀 BOT RUNNING FULL VERSION")

    app.run_polling()

if __name__ == "__main__":
    main()