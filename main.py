import sqlite3
import requests
import logging
import time
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- কনফিগারেশন (আপনার নতুন টোকেন ও আইডি) ---
BOT_TOKEN = "8055526604:AAEq30KmGRaxRJXh7RCMoYj36mTdZilToZI"
ADMIN_ID = 6928091474
LOG_CHANNEL = -1003725140237
WELCOME_PIC = "https://i.postimg.cc/qvcLFtWx/default-profile.jpg"

# লগিং কনফিগার
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- প্রিমিয়াম ডাটাবেজ ক্লাস ---
class GSMDatabase:
    def __init__(self):
        self.conn = sqlite3.connect("gsm_v13_beast.db", check_same_thread=False)
        self.cur = self.conn.cursor()
        self.cur.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, 
            approved INTEGER DEFAULT 0, 
            limit_count INTEGER DEFAULT 0, 
            used INTEGER DEFAULT 0)""")
        self.conn.commit()

    def add_user(self, uid):
        self.cur.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (uid,))
        self.conn.commit()

    def get_info(self, uid):
        self.cur.execute("SELECT approved, limit_count, used FROM users WHERE id=?", (uid,))
        return self.cur.fetchone()

    def set_limit(self, uid, count):
        self.cur.execute("UPDATE users SET approved=1, limit_count=?, used=0 WHERE id=?", (count, uid))
        self.conn.commit()

    def update_usage(self, uid):
        self.cur.execute("UPDATE users SET used = used + 1 WHERE id=?", (uid,))
        self.conn.commit()

    def reset_user(self, uid):
        self.cur.execute("UPDATE users SET approved=0, limit_count=0, used=0 WHERE id=?", (uid,))
        self.conn.commit()

db = GSMDatabase()

# --- প্রোগ্রেস মিটার ---
def create_meter(current, total):
    try:
        perc = (current / total) * 100
        filled = int(perc / 10)
        bar = "💠" * filled + "💿" * (10 - filled)
        return f"{bar} {perc:.1f}%"
    except: return "⏳ প্রসেসিং..."

# --- সুপার কার্ড ম্যানেজার ---
async def send_fancy_card(chat_id, context, title, text, show_req=False):
    kb = [[InlineKeyboardButton("👨‍💻 Admin", url=f"tg://user?id={ADMIN_ID}")]]
    if show_req:
        kb.insert(0, [InlineKeyboardButton("📩 অনুমতি নিন", callback_data=f"req_{chat_id}")])
    try:
        await context.bot.send_photo(
            chat_id=chat_id, photo=WELCOME_PIC, 
            caption=f"**{title}**\n\n{text}", 
            reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
        )
    except: pass

# --- হাই-স্পিড ডাউনলোড ইঞ্জিন ---
async def start_download(url, context, chat_id, msg_id, f_path):
    start = time.time()
    try:
        r = requests.get(url, stream=True, timeout=120)
        total = int(r.headers.get('content-length', 0))
        done = 0
        last_up = 0
        with open(f_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024*1024):
                if chunk:
                    f.write(chunk)
                    done += len(chunk)
                    if time.time() - last_up > 3.0:
                        speed = done / (time.time() - start) / (1024 * 1024)
                        status = (f"🚀 **GSM PREMIUM SPEED** 🚀\n\n{create_meter(done, total)}\n\n"
                                  f"🛰 স্পিড: `{speed:.2f} MB/s`\n"
                                  f"📦 ডাটা: `{done/(1024*1024):.1f}MB` / `{total/(1024*1024):.1f}MB`")
                        try: await context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=status, parse_mode="Markdown")
                        except: pass
                        last_up = time.time()
        return True
    except: return False

# --- মূল হ্যান্ডলার ---
async def gsm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text

    # ১. এডমিন কন্ট্রোল
    if uid == ADMIN_ID:
        if 'rep_to' in context.user_data:
            tid = context.user_data.pop('rep_to')
            await send_fancy_card(tid, context, "📩 এডমিন থেকে মেসেজ", text)
            await update.message.reply_text("✅ মেসেজ পাঠানো হয়েছে।")
            return
        if 'lim_to' in context.user_data:
            tid = context.user_data.pop('lim_to')
            if text.isdigit():
                db.set_limit(tid, int(text))
                await update.message.reply_text(f"✅ ইউজার `{tid}` অনুমোদিত। লিমিট: {text} টি।")
                await send_fancy_card(tid, context, "🎉 অ্যাক্সেস কনফার্ম!", f"এডমিন আপনাকে অনুমতি দিয়েছেন। লিমিট: {text} টি।")
            return

    # ২. লিঙ্ক ডিটেকশন
    if "tiktok.com" in text:
        info = db.get_info(uid)
        if not info or info[0] == 0 or info[2] >= info[1]:
            await send_fancy_card(uid, context, "⚠️ অ্যাক্সেস নেই", "আপনার লিমিট শেষ অথবা অনুমতি নেই।", True)
            return

        context.user_data['temp_url'] = text
        m = await update.message.reply_text("🔍 তথ্য সংগ্রহ করছি...")
        try:
            api = requests.get(f"https://www.tikwm.com/api/?url={text}").json()["data"]
            context.bot_data[f"raw_{uid}"] = api
            kb = [[InlineKeyboardButton("🎬 Video (HD)", callback_data=f"dl_v_{uid}"), 
                   InlineKeyboardButton("🎵 Audio", callback_data=f"dl_a_{uid}")]]
            if api.get("images"): kb.append([InlineKeyboardButton("🖼️ Photos", callback_data=f"dl_p_{uid}")])
            await context.bot.send_photo(chat_id=uid, photo=api['author']['avatar'], caption="ডাউনলোড ফরম্যাট বেছে নিন:", reply_markup=InlineKeyboardMarkup(kb))
            await m.delete()
        except: await m.edit_text("❌ লিঙ্কে সমস্যা আছে।")

# --- ক্যালব্যাক প্রসেস ---
async def gsm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data, uid = query.data, query.from_user.id
    p_link = f"[{uid}](tg://user?id={uid})"
    await query.answer()

    if data.startswith("req_"):
        txt = f"🔔 **নতুন রিকোয়েস্ট!**\n👤 নাম: {query.from_user.full_name}\n🆔 আইডি: {p_link}"
        kb = [[InlineKeyboardButton("✅ অনুমতি দিন", callback_data=f"conf_{uid}")]]
        await context.bot.send_message(chat_id=ADMIN_ID, text=txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        await query.edit_message_caption(caption="✅ রিকোয়েস্ট পাঠানো হয়েছে।")

    elif data.startswith("conf_"):
        tid = data.split("_")[1]
        context.user_data['lim_to'] = tid
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"আইডি `{tid}` এর জন্য লিমিট সংখ্যা দিন:")

    elif data.startswith("action_"):
        tid = data.split("_")[1]
        kb = [[InlineKeyboardButton("💬 রিপ্লাই", callback_data=f"rep_{tid}"), 
               InlineKeyboardButton("❌ ব্লক/ক্যানসেল", callback_data=f"can_{tid}")]]
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🛠 **ইউজার কন্ট্রোল: {tid}**", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("rep_"):
        context.user_data['rep_to'] = data.split("_")[1]
        await context.bot.send_message(chat_id=ADMIN_ID, text="👤 আপনার মেসেজটি লিখুন:")

    elif data.startswith("can_"):
        tid = data.split("_")[1]
        db.reset_user(tid)
        await send_fancy_card(tid, context, "❌ লিমিট বাতিল", "এডমিন আপনার অ্যাক্সেস বন্ধ করেছেন।", True)
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"✅ ইউজার `{tid}` ব্লক করা হয়েছে।")

    elif data.startswith("dl_"):
        mode, tid = data.split("_")[1], int(data.split("_")[2])
        raw = context.bot_data.get(f"raw_{tid}")
        orig_url = context.user_data.get('temp_url', 'Unknown')
        if not raw: return

        p_msg = await context.bot.send_message(chat_id=tid, text="🚀 কানেক্ট হচ্ছে...")
        f_name = f"gsm_{tid}.mp4" if mode == 'v' else f"gsm_{tid}.mp3"
        d_url = raw['play'] if mode == 'v' else raw['music']

        success = False
        if mode in ['v', 'a']:
            if await start_download(d_url, context, tid, p_msg.message_id, f_name):
                await p_msg.edit_text("📤 আপলোড শুরু হচ্ছে...")
                if mode == 'v': await context.bot.send_video(chat_id=tid, video=open(f_name, 'rb'), caption="✅ GSM PRO - ভিডিও")
                else: await context.bot.send_audio(chat_id=tid, audio=open(f_name, 'rb'), caption="🎵 GSM PRO - অডিও")
                os.remove(f_name)
                success = True
        elif mode == 'p':
            media = [InputMediaPhoto(img) for img in raw['images'][:10]]
            await context.bot.send_media_group(chat_id=tid, media=media)
            success = True

        if success:
            await p_msg.delete()
            db.update_usage(tid)
            res = db.get_info(tid)
            rem = res[1] - res[2]

            # চ্যানেল রিপোর্ট (প্রোফাইল বাটন সহ)
            kb_log = [[InlineKeyboardButton(f"👤 প্রোফাইল (ID: {tid})", url=f"tg://user?id={tid}")],
                      [InlineKeyboardButton("🛠 অ্যাকশন নিন", callback_data=f"action_{tid}")] ]
            log_cap = (f"📥 **ডাউনলোড রিপোর্ট**\n\n🎬 টাইপ: {mode}\n📊 অবশিষ্ট: **{rem}** টি\n🔗 লিঙ্ক: {orig_url}")
            await context.bot.send_photo(chat_id=LOG_CHANNEL, photo=WELCOME_PIC, caption=log_cap, reply_markup=InlineKeyboardMarkup(kb_log))

# --- রান ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", lambda u, c: (db.add_user(u.effective_user.id), send_fancy_card(u.effective_user.id, c, "✨ স্বাগতম", "অনুমতি নিতে নিচের বাটনে চাপ দিন।", True))))
    app.add_handler(CallbackQueryHandler(gsm_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gsm_handler))
    print("🔥 GSM Ultra Beast V13 is Active! 🔥")
    app.run_polling()
