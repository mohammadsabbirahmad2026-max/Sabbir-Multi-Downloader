import logging
import asyncio
import yt_dlp
import datetime
import sqlite3
import os
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from keep_alive import keep_alive

# --- লগিং কনফিগারেশন ---
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- কনফিগারেশন ---
BOT_TOKEN = "8363612564:AAGZDZZbyoaxS3V6PJZ7w0CdCgZ_scKP6o8"
ADMIN_ID = 6928091474 
GEMINI_KEY = "AIzaSyCkuQjBT41-PpFUSVpHc2zw5qB4AURReQ4"
IMAGE_URL = "https://i.postimg.cc/qvcLFtWx/default-profile.jpg"
DEV_NAME = "Mohammad Sabbir Ahmad"

# --- জেমিনি প্রফেশনাল সেটআপ ---
genai.configure(api_key=GEMINI_KEY)
# জেমিনি মডেল সেটিংস
model = genai.GenerativeModel(
    model_name='gemini-1.5-flash',
    safety_settings={
        "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
        "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
        "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
    }
)
chat_sessions = {}

# --- ডাটাবেস ম্যানেজমেন্ট ---
class Database:
    def __init__(self):
        self.db_path = "master_bot.db"
        self._create_tables()

    def _get_conn(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _create_tables(self):
        with self._get_conn() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, uname TEXT, date TEXT)")
            conn.commit()

    def register_user(self, uid, name, uname):
        with self._get_conn() as conn:
            conn.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)", 
                         (uid, name, uname, datetime.datetime.now().strftime("%Y-%m-%d")))
            conn.commit()

db = Database()

# --- স্মার্ট ডাউনলোড ইঞ্জিন ---
class ProDownloader:
    @staticmethod
    async def fetch_info(url):
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': 'best[ext=mp4]/best', # MP4 নিশ্চিত করা হয়েছে
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
            'cachedir': False,
            'noplaylist': True
        }
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=False))
        except Exception as e:
            logger.error(f"YT-DLP Error: {e}")
            return None

# --- UI হেল্পার ---
class UI:
    @staticmethod
    def main_kb(uid):
        buttons = [['👤 My Profile', '🆘 Support'], ['📜 History']]
        if uid == ADMIN_ID:
            buttons.insert(0, ['📊 Statistics', '📢 Broadcast'])
        return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# --- কোর হ্যান্ডেলারস ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.register_user(user.id, user.full_name, user.username)
    
    msg = (f"🚀 **Ultimate Multi-Downloader AI**\n"
           f"━━━━━━━━━━━━━━━━━━\n"
           f"👨‍💻 **Developer:** [{DEV_NAME}](tg://user?id={ADMIN_ID})\n"
           f"🧠 **AI Brain:** Gemini 1.5 Flash\n"
           f"━━━━━━━━━━━━━━━━━━\n"
           f"যেকোনো লিঙ্ক পাঠান অথবা আমার সাথে গল্প করুন!")
    
    await update.message.reply_photo(
        photo=IMAGE_URL, 
        caption=msg, 
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=UI.main_kb(user.id)
    )

async def handle_core(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text
    state = context.user_data.get('state')

    if text == '🔙 Back to Menu' or text == '❌ Cancel':
        context.user_data['state'] = None
        await update.message.reply_text("🏠 মূল মেনু:", reply_markup=UI.main_kb(uid))
        return

    # ব্রডকাস্ট লজিক
    if uid == ADMIN_ID and text == '📢 Broadcast':
        context.user_data['state'] = 'bc'
        await update.message.reply_text("📢 ব্রডকাস্ট মেসেজটি লিখুন:", reply_markup=ReplyKeyboardMarkup([['❌ Cancel']], resize_keyboard=True))
        return

    if state == 'bc' and uid == ADMIN_ID:
        with sqlite3.connect("master_bot.db") as conn:
            users = conn.execute("SELECT id FROM users").fetchall()
        
        count = 0
        for u in users:
            try:
                await update.message.copy(chat_id=u[0])
                count += 1
                await asyncio.sleep(0.05) # ফ্লাডিং এড়াতে
            except: pass
        
        context.user_data['state'] = None
        await update.message.reply_text(f"✅ {count} জন ইউজারকে পাঠানো হয়েছে।", reply_markup=UI.main_kb(uid))
        return

    # ডাউনলোড লজিক
    if "http" in text:
        wait = await update.message.reply_text("📡 **Analyzing Link...**", parse_mode=ParseMode.MARKDOWN)
        info = await ProDownloader.fetch_info(text)
        
        if info:
            v_id = info.get('id', str(datetime.datetime.now().timestamp()))
            # মেমোরি সেভ করতে শুধু প্রয়োজনীয় ডাটা রাখা হচ্ছে
            context.user_data[v_id] = {'u': info.get('url'), 't': info.get('title'), 's': text}
            
            kb = [[InlineKeyboardButton("🎬 Video", callback_data=f"dl_v_{v_id}"),
                   InlineKeyboardButton("🎵 Audio", callback_data=f"dl_a_{v_id}")]]
            
            await wait.delete()
            await update.message.reply_photo(
                photo=info.get('thumbnail', IMAGE_URL),
                caption=f"📝 **Title:** {info.get('title')[:100]}\n\n✅ Platform: {info.get('extractor_key')}\n🛠 Dev: {DEV_NAME}",
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await wait.edit_text("❌ লিঙ্কে মিডিয়া পাওয়া যায়নি। সঠিক লিঙ্ক দিন।")
        return

    # জেমিনি এআই চ্যাট
    if text:
        thinking = await update.message.reply_text("💭")
        try:
            if uid not in chat_sessions:
                chat_sessions[uid] = model.start_chat(history=[])
            
            response = chat_sessions[uid].send_message(text)
            if response.text:
                await thinking.edit_text(f"{response.text}\n\n✨ _Powered by {DEV_NAME}_", parse_mode=ParseMode.MARKDOWN)
            else:
                await thinking.edit_text("💡 আমি এই প্রশ্নের উত্তর দিতে পারছি না। অন্য কিছু জিজ্ঞাসা করুন।")
        except Exception as e:
            logger.error(f"Gemini Error: {e}")
            await thinking.edit_text("💡 আমি এখন কিছুটা ব্যস্ত। পরে আবার চ্যাট করুন।")

async def callback_processor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    await query.answer()
    
    # maxsplit=2 ব্যবহার করা হয়েছে যাতে আইডিতে আন্ডারস্কোর থাকলেও সমস্যা না হয়
    parts = query.data.split("_", 2)
    if len(parts) < 3: return
    
    mode = parts[1]
    v_id = parts[2]
    
    f_info = context.user_data.get(v_id)
    if not f_info:
        await query.message.reply_text("❌ সেশন শেষ! আবার লিঙ্ক পাঠান।")
        return

    # অ্যাডমিন রিপোর্ট
    await context.bot.send_message(ADMIN_ID, f"📥 **Download Alert**\nUser: {query.from_user.full_name}\nLink: {f_info['s']}")

    status = await query.message.reply_text("⚡ **Uploading...**")
    try:
        if mode == 'v':
            await query.message.reply_video(video=f_info['u'], caption=f"✅ {f_info['t']}\n\nDev: {DEV_NAME}")
        else:
            await query.message.reply_audio(audio=f_info['u'], title=f_info['t'])
        await status.delete()
        # পাঠানো শেষ হলে মেমোরি থেকে ডাটা ডিলিট করা হচ্ছে (র‍্যাম সেভ করতে)
        del context.user_data[v_id]
    except Exception as e:
        logger.error(f"Upload Error: {e}")
        await status.edit_text("❌ ফাইলটি টেলিগ্রাম লিমিটের বাইরে অথবা লিঙ্ক এক্সপায়ার হয়েছে।")

if __name__ == '__main__':
    keep_alive()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_core))
    app.add_handler(CallbackQueryHandler(callback_processor))
    
    print(f"🔥 Master Bot Live! Developer: {DEV_NAME}")
    app.run_polling()
