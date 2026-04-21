import logging
import asyncio
import yt_dlp
import datetime
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from keep_alive import keep_alive

# লগিং ও কনফিগারেশন
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
BOT_TOKEN = "8363612564:AAGZDZZbyoaxS3V6PJZ7w0CdCgZ_scKP6o8"
ADMIN_ID = 6928091474 # আপনার আইডি

# --- ডাটাবেস সেটআপ (প্রাইভেসি ও ট্র্যাকিং) ---
db = sqlite3.connect("universal_bot.db", check_same_thread=False)
cur = db.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, name TEXT, username TEXT, join_date TEXT)""")
cur.execute("""CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER, platform TEXT, link TEXT, time TEXT)""")
db.commit()

# --- কিবোর্ড মেনু ---
def get_main_menu(uid):
    if uid == ADMIN_ID:
        keyboard = [['📊 Bot Stats', '📢 Broadcast'], ['👤 My Profile', '🛠 Settings']]
    else:
        keyboard = [['👤 My Profile', '📜 History'], ['🆘 Support']]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- ভিডিও ডাউনলোডার ফাংশন ---
def get_info(url):
    ydl_opts = {'quiet': True, 'no_warnings': True, 'format': 'best'}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try: return ydl.extract_info(url, download=False)
        except: return None

# --- হ্যান্ডেলারস ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    dt = datetime.datetime.now().strftime("%d-%m-%Y")
    cur.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)", (user.id, user.full_name, user.username, dt))
    db.commit()
    
    await update.message.reply_text(
        f"👋 **Welcome {user.first_name}!**\nআমি সব সোশ্যাল মিডিয়া থেকে ভিডিও ডাউনলোড করতে পারি। লিঙ্ক পাঠান!",
        reply_markup=get_main_menu(user.id), parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text

    # ১. এডমিন স্ট্যাটাস চেক
    if text == '📊 Bot Stats' and uid == ADMIN_ID:
        cur.execute("SELECT COUNT(*) FROM users")
        total_users = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM logs")
        total_dl = cur.fetchone()[0]
        await update.message.reply_text(f"📈 **Bot Statistics**\n\n👥 Total Users: {total_users}\n📥 Total Downloads: {total_dl}", parse_mode="Markdown")
        return

    # ২. ব্রডকাস্ট (সব ইউজারকে মেসেজ পাঠানো)
    if text == '📢 Broadcast' and uid == ADMIN_ID:
        await update.message.reply_text("📢 আপনার মেসেজটি লিখুন:")
        context.user_data['mode'] = 'bc'
        return

    if context.user_data.get('mode') == 'bc' and uid == ADMIN_ID:
        cur.execute("SELECT id FROM users")
        all_users = cur.fetchall()
        for u in all_users:
            try: await update.message.copy(chat_id=u[0])
            except: pass
        await update.message.reply_text("✅ ব্রডকাস্ট সম্পন্ন হয়েছে।")
        context.user_data['mode'] = None
        return

    # ৩. ইউনিভার্সাল ডাউনলোড লজিক
    if "http" in text:
        msg = await update.message.reply_text("🔍 Analyzing...")
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, get_info, text)

        if info:
            v_id = info.get('id')
            context.user_data[v_id] = info
            platform = info.get('extractor_key', 'Unknown')
            
            # ডাটাবেসে লগ রাখা (এডমিন চেক করতে পারবে)
            cur.execute("INSERT INTO logs (uid, platform, link, time) VALUES (?, ?, ?, ?)", 
                        (uid, platform, text, datetime.datetime.now().strftime("%H:%M %d-%m")))
            db.commit()

            # এডমিনকে নোটিফিকেশন পাঠানো (প্রাইভেসি মেইনটেইন করে)
            await context.bot.send_message(ADMIN_ID, f"📥 **New Download**\n👤 User: {update.effective_user.first_name}\n🌐 Site: {platform}")

            kb = [[InlineKeyboardButton("🎬 Video", callback_data=f"dl_v_{v_id}"),
                   InlineKeyboardButton("🎵 Audio", callback_data=f"dl_a_{v_id}")]]
            await msg.delete()
            await update.message.reply_photo(photo=info.get('thumbnail'), caption=f"📝 {info.get('title')[:50]}", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await msg.edit_text("❌ লিঙ্কে সমস্যা আছে।")

async def callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, type, v_id = query.data.split("_")
    info = context.user_data.get(v_id)

    if info:
        if type == "v": await query.message.reply_video(video=info['url'])
        else: await query.message.reply_audio(audio=info['url'])

if __name__ == '__main__':
    keep_alive() # রেন্ডারের জন্য
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(callback_query))
    print("🚀 Bot Started!")
    app.run_polling()
    
