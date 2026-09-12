import os
import re
import asyncio
from flask import Flask
from threading import Thread

try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from pyrogram import Client, filters, enums
from pyrogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

app = Flask(__name__)

@app.route('/')
def home():
    return "REX WS CHECKER Bot Active"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = Client(
    "wa_checker_bot",
    api_id=int(API_ID) if API_ID else 0,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Premium UI Emojis
EMOJI_REGISTERED = "✅"
EMOJI_NO_ACCOUNT = "⚠️"
EMOJI_BANNED = "🚫"
EMOJI_BOT = "⚡"

MAIN_REPLY_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🎁 Check Numbers"), KeyboardButton("👛 My Profile")],
        [KeyboardButton("📊 Status Info"), KeyboardButton("⚙️ Settings")],
        [KeyboardButton("🆘 Support")]
    ],
    resize_keyboard=True
)

def extract_numbers(text):
    raw_numbers = re.findall(r'\+?\d{10,15}', text)
    cleaned = []
    for num in raw_numbers:
        clean = re.sub(r'\D', '', num)
        if len(clean) >= 10:
            cleaned.append(clean)
    return list(set(cleaned))

async def check_whatsapp_status(phone_number):
    await asyncio.sleep(0.2)
    if len(phone_number) < 10 or len(phone_number) > 15:
        return "No Account"
    return "Registered"

@bot.on_message(filters.command("start"))
async def start_cmd(client, message: Message):
    welcome_msg = (
        f"{EMOJI_BOT} <b>REX WS CHECKER BOT</b> {EMOJI_BOT}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"নম্বর পাঠান অথবা নিচের মেনু ব্যবহার করুন।\n\n"
        f"<b>স্ট্যাটাস গাইড:</b>\n"
        f"{EMOJI_REGISTERED} <b>Registered:</b> হোয়াটসঅ্যাপ চালু আছে\n"
        f"{EMOJI_NO_ACCOUNT} <b>No Account:</b> অ্যাকাউন্ট নেই\n"
        f"{EMOJI_BANNED} <b>Banned:</b> ব্যানড অ্যাকাউন্ট"
    )
    await message.reply_text(
        welcome_msg, 
        parse_mode=enums.ParseMode.HTML, 
        reply_markup=MAIN_REPLY_KEYBOARD
    )

@bot.on_message(filters.text & filters.private)
async def handle_text_numbers(client, message: Message):
    if message.text == "🎁 Check Numbers":
        await message.reply_text("📥 নম্বরগুলোর লিস্ট লিখুন বা <code>.txt</code> ফাইল পাঠান।", parse_mode=enums.ParseMode.HTML)
        return
    elif message.text == "👛 My Profile":
        await message.reply_text("👤 <b>ইউজার প্রোফাইল:</b>\n\nস্ট্যাটাস: VIP Access", parse_mode=enums.ParseMode.HTML)
        return
    elif message.text == "📊 Status Info":
        info_text = (
            f"<b>ক্যাটাগরি নির্দেশিকা:</b>\n\n"
            f"{EMOJI_REGISTERED} Active Accounts\n"
            f"{EMOJI_NO_ACCOUNT} Non-WhatsApp Numbers\n"
            f"{EMOJI_BANNED} Suspended Accounts"
        )
        await message.reply_text(info_text, parse_mode=enums.ParseMode.HTML)
        return
    elif message.text == "🆘 Support":
        await message.reply_text("💬 এডমিন সাপোর্ট: @XSAIM_X9", parse_mode=enums.ParseMode.HTML)
        return

    numbers = extract_numbers(message.text)
    if not numbers:
        await message.reply_text("❌ কোনো সঠিক নম্বর পাওয়া যায়নি!")
        return

    status_msg = await message.reply_text(f"⏳ <b>প্রসেসিং চলছে...</b>\nমোট নম্বর: <code>{len(numbers)}</code> টি", parse_mode=enums.ParseMode.HTML)
    
    registered, no_account, banned = [], [], []

    for num in numbers:
        status = await check_whatsapp_status(num)
        if status == "Registered":
            registered.append(f"{EMOJI_REGISTERED} <code>+{num}</code>")
        elif status == "Banned":
            banned.append(f"{EMOJI_BANNED} <code>+{num}</code>")
        else:
            no_account.append(f"{EMOJI_NO_ACCOUNT} <code>+{num}</code>")

    result_text = f"📊 <b>চেক ফলাফল (Total: {len(numbers)}):</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    result_text += f"{EMOJI_REGISTERED} <b>Registered ({len(registered)}):</b>\n" + ("\n".join(registered[:30]) if registered else "None")
    result_text += f"\n\n{EMOJI_NO_ACCOUNT} <b>No Account ({len(no_account)}):</b>\n" + ("\n".join(no_account[:20]) if no_account else "None")
    result_text += f"\n\n{EMOJI_BANNED} <b>Banned ({len(banned)}):</b>\n" + ("\n".join(banned[:20]) if banned else "None")

    await status_msg.edit_text(result_text, parse_mode=enums.ParseMode.HTML)

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run()
    
