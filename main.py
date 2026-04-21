import logging
import asyncio
import yt_dlp
import datetime
import sqlite3
import os
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from keep_alive import keep_alive

# --- লগিং সেটআপ ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- কনফিগারেশন ---
BOT_TOKEN = "8363612564:AAHWd_YIubc7LWbBnxWhONSigTYGVSR5JOs"
ADMIN_ID = 6928091474 
GEMINI_KEY = "AIzaSyCkuQjBT41-PpFUSVpHc2zw5qB4AURReQ4"
IMAGE_URL = "https://i.postimg.cc/qvcLFtWx/default-profile.jpg"
DEV_NAME = "Mohammad Sabbir Ahmad"

# --- জেমিনি এআই ইঞ্জিন ---
genai.configure(api_key=GEMINI_KEY)
# জেমিনি সেটিংস: এটি যাতে ফিল্টার না করে সব উত্তর দেয়
generation_config = {
    "temperature": 0.9,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 2048,
}
model = genai.GenerativeModel(
    model_name='gemini-1.5-flash',
    generation_config=generation_config,
    safety_settings=[
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]
)
chat_sessions = {}

# --- ডাটাবেস সিস্টেম (Thread-Safe) ---
class Database:
    def __init__(self):
        self.db_path = "master_bot.db"
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS users 
                         (id INTEGER PRIMARY KEY, name TEXT, uname TEXT, date TEXT)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS stats 
                         (key TEXT PRIMARY KEY, value INTEGER)""")
            conn.commit()

    def register_user(self, uid, name, uname):
        with self._get_connection() as conn:
            conn.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)", 
                         (uid, name, uname, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
            conn.commit()

    def get_all_users(self):
        with self._get_connection() as conn:
            return conn.execute("SELECT id FROM users").fetchall()

db = Database()

# --- উন্নত মাল্টি-ডাউনলোডার ইঞ্জিন (TikTok/FB/YT/Insta) ---
class DownloaderEngine:
    @staticmethod
    async def get_info(url):
        # টিকটক এবং অন্যান্য প্ল্যাটফর্মের জন্য স্পেশাল ইউজার এজেন্ট
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': 'best',
            'cachedir': False,
            'noplaylist': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
        try:
            loop = asyncio.get_event_loop()
            # এখানে 'download=False' মানে আমরা শুধু ভিডিও লিঙ্ক ও তথ্য বের করছি
            return await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=False))
        except Exception as e:
            logger.error(f"Engine Error: {e}")
            return None

# --- UI এবং বাটন কন্ট্রোলার ---
class UI:
    @staticmethod
    def main_menu(uid):
        kb = [['👤 My Profile', '🆘 Support'], ['📜 Download History', '🧠 AI Chat']]
        if uid == ADMIN_ID:
            kb.insert(0, ['📊 Statistics', '📢 Broadcast'])
        return ReplyKeyboardMarkup(kb, resize_keyboard=True)

    @staticmethod
    def cancel_kb():
        return ReplyKeyboardMarkup([['❌ Cancel Operation']], resize_keyboard=True)

# --- কোর ফাংশনালিটি (হ্যান্ডেলার্স) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.register_user(user.id, user.full_name, user.username)
    
    msg = (f"👋 **আসসালামু আলাইকুম, {user.first_name}!**\n\n"
           f"🚀 **Master Multi-Downloader AI-তে স্বাগতম।**\n"
           f"━━━━━━━━━━━━━━━━━━\n"
           f"✅ **সাপোর্টেড:** YouTube, TikTok, FB, Insta, Twitter\n"
           f"🧠 **AI:** জেমিনি ১.৫ আল্ট্রা ফাস্ট\n"
           f"👨‍💻 **Dev:** [{DEV_NAME}](tg://user?id={ADMIN_ID})\n"
           f"━━━━━━━━━━━━━━━━━━\n"
           f"যেকোনো ভিডিও লিঙ্ক দিন অথবা নিচে মেনু থেকে অপশন বেছে নিন।")
    
    await update.message.reply_photo(
        photo=IMAGE_URL, 
        caption=msg, 
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=UI.main_menu(user.id)
    )

async def global_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text
    state = context.user_data.get('state')

    # ক্যানসেল অপারেশন
    if text == '❌ Cancel Operation' or text == '/cancel':
        context.user_data['state'] = None
        await update.message.reply_text("🏠 অপারেশন বাতিল করা হয়েছে। মূল মেনু:", reply_markup=UI.main_menu(uid))
        return

    # অ্যাডমিন ব্রডকাস্ট সেকশন
    if uid == ADMIN_ID and text == '📢 Broadcast':
        context.user_data['state'] = 'await_bc'
        await update.message.reply_text("📢 আপনার মেসেজটি লিখুন যা সবাইকে পাঠাতে চান:", reply_markup=UI.cancel_kb())
        return

    if state == 'await_bc' and uid == ADMIN_ID:
        users = db.get_all_users()
        sent = 0
        status_msg = await update.message.reply_text("📤 ব্রডকাস্টিং শুরু হয়েছে...")
        for u in users:
            try:
                await update.message.copy(chat_id=u[0])
                sent += 1
                await asyncio.sleep(0.05)
            except: pass
        context.user_data['state'] = None
        await status_msg.edit_text(f"✅ সফলভাবে {sent} জন ইউজারের কাছে পাঠানো হয়েছে।")
        await update.message.reply_text("মূল মেনু:", reply_markup=UI.main_menu(uid))
        return

    # ডাউনলোড ইঞ্জিন হ্যান্ডলার (লিঙ্ক শনাক্তকরণ)
    if "http" in text:
        wait_msg = await update.message.reply_text("🔍 **লিঙ্ক এনালাইজ করছি... একটু অপেক্ষা করুন।**", parse_mode=ParseMode.MARKDOWN)
        info = await DownloaderEngine.get_info(text)
        
        if info:
            v_id = info.get('id', str(datetime.datetime.now().timestamp()))
            # মেমোরি ম্যানেজমেন্টের জন্য ডাটা সেভ
            context.user_data[v_id] = {
                'url': info.get('url'),
                'title': info.get('title', 'No Title'),
                'thumb': info.get('thumbnail', IMAGE_URL),
                'platform': info.get('extractor_key', 'Unknown')
            }
            
            kb = [
                [InlineKeyboardButton("🎬 Video Download", callback_data=f"dl_vid_{v_id}")],
                [InlineKeyboardButton("🎵 Audio (MP3)", callback_data=f"dl_aud_{v_id}")]
            ]
            
            await wait_msg.delete()
            caption = (f"📝 **Title:** {info.get('title')[:100]}...\n\n"
                       f"🌐 **Platform:** {info.get('extractor_key')}\n"
                       f"👨‍💻 **Developer:** {DEV_NAME}")
            
            await update.message.reply_photo(
                photo=info.get('thumbnail', IMAGE_URL),
                caption=caption,
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await wait_msg.edit_text("❌ দুঃখিত! এই লিঙ্ক থেকে তথ্য পাওয়া যায়নি। লিঙ্কটি চেক করুন (TikTok বা FB এর ক্ষেত্রে নিশ্চিত হোন এটি পাবলিক)।")
        return

    # AI চ্যাট হ্যান্ডলার
    if text and state != 'await_bc':
        thinking = await update.message.reply_text("💭")
        try:
            if uid not in chat_sessions:
                chat_sessions[uid] = model.start_chat(history=[])
            
            response = chat_sessions[uid].send_message(text)
            ai_reply = f"{response.text}\n\n✨ _Powered by {DEV_NAME}_"
            await thinking.edit_text(ai_reply, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Gemini Error: {e}")
            await thinking.edit_text("💡 আমি এখন কিছুটা ক্লান্ত। দয়া করে কিছুক্ষণ পর আবার মেসেজ দিন।")

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()
    
    # ডাটা স্প্লিট (dl_vid_id)
    parts = data.split("_", 2)
    mode = parts[1] # vid or aud
    v_id = parts[2]
    
    video_data = context.user_data.get(v_id)
    if not video_data:
        await query.message.reply_text("❌ সেশন শেষ হয়ে গেছে। দয়া করে আবার লিঙ্কটি পাঠান।")
        return

    # অ্যাডমিনকে রিপোর্ট পাঠানো
    report = f"📥 **Download Activity**\nUser: {query.from_user.full_name}\nPlatform: {video_data['platform']}"
    await context.bot.send_message(ADMIN_ID, report)

    status = await query.message.reply_text("⚡ **প্রসেস করছি এবং টেলিগ্রামে আপলোড দিচ্ছি...**")
    
    try:
        if mode == 'vid':
            await query.message.reply_video(
                video=video_data['url'], 
                caption=f"✅ **{video_data['title']}**\n\n📥 Downloaded via @{context.bot.username}\n🛠 Dev: {DEV_NAME}",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await query.message.reply_audio(
                audio=video_data['url'], 
                title=video_data['title'],
                caption=f"🎵 Audio Extracted by {DEV_NAME}"
            )
        await status.delete()
        # কাজ শেষে মেমোরি থেকে ডাটা ডিলিট (বট যাতে স্লো না হয়)
        del context.user_data[v_id]
    except Exception as e:
        logger.error(f"Upload Error: {e}")
        await status.edit_text("❌ ফাইলটি অনেক বড় অথবা টেলিগ্রাম সার্ভার এই মুহূর্তে ফাইলটি নিতে পারছে না।")

if __name__ == '__main__':
    # রেন্ডারে বট ২৪/৭ সচল রাখার জন্য
    keep_alive()
    
    # অ্যাপ্লিকেশন বিল্ড
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # হ্যান্ডেলার রেজিস্টার
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", global_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, global_handler))
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    
    print(f"✅ {DEV_NAME}-এর মাস্টার বট সচল হয়েছে...")
    app.run_polling()
