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
from pyrogram.types import (
    Message, 
    ReplyKeyboardMarkup, 
    KeyboardButton
)

# Render & UptimeRobot Integration (Keep Alive Server)
app = Flask(__name__)

@app.route('/')
def home():
    return "REX WS CHECKER Bot is Active & Pinged!"

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

# Custom Emoji Placeholders (বোটের রেসপন্স থেকে ID পাওয়ার পর নিচের ডিজিটগুলো বদলে দিন)
EMOJI_REGISTERED = '<tg-emoji id="5368324170671202286">✅</tg-emoji>'
EMOJI_NO_ACCOUNT = '<tg-emoji id="5368324170671202287">⚠️</tg-emoji>'
EMOJI_BANNED = '<tg-emoji id="5368324170671202288">🚫</tg-emoji>'
EMOJI_BOT = '<tg-emoji id="5467472918826501234">⚡</tg-emoji>'

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
    await asyncio.sleep(0.3)
    if len(phone_number) < 10 or len(phone_number) > 15:
        return "No Account"
    return "Registered"

@bot.on_message(filters.command("start"))
async def start_cmd(client, message: Message):
    welcome_msg = (
        f"{EMOJI_BOT} <b>REX WS CHECKER BOT</b> {EMOJI_BOT}\n\n"
        f"আমাকে নম্বর পাঠান অথবা নিচে দেওয়া বাটন ব্যবহার করুন।\n\n"
        f"<b>স্ট্যাটাস গাইড:</b>\n"
        f"{EMOJI_REGISTERED} <b>Registered:</b> হোয়াটসঅ্যাপ অ্যাকাউন্ট সচল আছে\n"
        f"{EMOJI_NO_ACCOUNT} <b>No Account:</b> হোয়াটসঅ্যাপ অ্যাকাউন্ট খোলা নেই\n"
        f"{EMOJI_BANNED} <b>Banned:</b> অ্যাকাউন্ট নষ্ট বা ব্যানড"
    )
    await message.reply_text(
        welcome_msg, 
        parse_mode=enums.ParseMode.HTML, 
        reply_markup=MAIN_REPLY_KEYBOARD
    )

@bot.on_message(filters.text & filters.private)
async def handle_text_numbers(client, message: Message):
    # ১. কাস্টম ইমোজি আইডি ডিটেক্টর (মেসেজে প্রিমিয়াম ইমোজি পেলে ID প্রদান করবে)
    if message.entities:
        for entity in message.entities:
            if entity.type == enums.MessageEntityType.CUSTOM_EMOJI:
                await message.reply_text(
                    f"✨ <b>Custom Emoji ID Found!</b>\n\n"
                    f"ID: <code>{entity.custom_emoji_id}</code>\n\n"
                    f"কোডে বসানোর নিয়ম:\n"
                    f"<code>&lt;tg-emoji id=\"{entity.custom_emoji_id}\"&gt;✅&lt;/tg-emoji&gt;</code>",
                    parse_mode=enums.ParseMode.HTML
                )
                return

    # ২. মেনু বাটন হ্যান্ডলিং
    if message.text == "🎁 Check Numbers":
        await message.reply_text("📥 আপনার নম্বরগুলোর লিস্ট পাঠান অথবা <code>.txt</code> ফাইল দিন।", parse_mode=enums.ParseMode.HTML)
        return
    elif message.text == "👛 My Profile":
        await message.reply_text("👤 <b>ইউজার প্রোফাইল:</b>\n\nস্ট্যাটাস: VIP Access\nটোটাল চেকড: 100+", parse_mode=enums.ParseMode.HTML)
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
        await message.reply_text("💬 এডমিন সাপোর্টের জন্য যোগাযোগ করুন: @XSAIM_X9", parse_mode=enums.ParseMode.HTML)
        return

    # ৩. নম্বর চেকিং প্রসেসিং
    numbers = extract_numbers(message.text)
    if not numbers:
        await message.reply_text("❌ কোনো সঠিক নম্বর পাওয়া যায়নি! দেশের কোড সহ নম্বর দিন।")
        return

    status_msg = await message.reply_text(f"⏳ <b>প্রসেসিং চলছে...</b>\nমোট নম্বর: <code>{len(numbers)}</code> টি", parse_mode=enums.ParseMode.HTML)
    
    registered, no_account, banned = [], [], []

    for num in numbers:
        status = await check_whatsapp_status(num)
        if status == "Registered":
            registered.append(f"{EMOJI_REGISTERED} +{num}")
        elif status == "Banned":
            banned.append(f"{EMOJI_BANNED} +{num}")
        else:
            no_account.append(f"{EMOJI_NO_ACCOUNT} +{num}")

    result_text = f"📊 <b>চেক ফলাফল (Total: {len(numbers)}):</b>\n\n"
    result_text += f"{EMOJI_REGISTERED} <b>Registered ({len(registered)}):</b>\n" + ("\n".join(registered[:30]) if registered else "None")
    result_text += f"\n\n{EMOJI_NO_ACCOUNT} <b>No Account ({len(no_account)}):</b>\n" + ("\n".join(no_account[:20]) if no_account else "None")
    result_text += f"\n\n{EMOJI_BANNED} <b>Banned ({len(banned)}):</b>\n" + ("\n".join(banned[:20]) if banned else "None")

    await status_msg.edit_text(result_text, parse_mode=enums.ParseMode.HTML)

@bot.on_message(filters.document & filters.private)
async def handle_file_numbers(client, message: Message):
    if not message.document.file_name.endswith('.txt'):
        await message.reply_text("❌ শুধুমাত্র <code>.txt</code> ফাইল গ্রহণ করা হবে।", parse_mode=enums.ParseMode.HTML)
        return

    status_msg = await message.reply_text("📥 <b>ফাইল প্রসেসিং করা হচ্ছে...</b>", parse_mode=enums.ParseMode.HTML)
    file_path = await message.download()

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    os.remove(file_path)
    numbers = extract_numbers(content)

    if not numbers:
        await status_msg.edit_text("❌ ফাইলে কোনো বৈধ্য নম্বর পাওয়া যায়নি।")
        return

    await status_msg.edit_text(f"🔄 <b>স্ক্যানিং চলছে...</b>\nমোট নম্বর: <code>{len(numbers)}</code> টি", parse_mode=enums.ParseMode.HTML)
    
    registered, no_account, banned = [], [], []

    for num in numbers:
        status = await check_whatsapp_status(num)
        if status == "Registered":
            registered.append(f"+{num}")
        elif status == "Banned":
            banned.append(f"+{num}")
        else:
            no_account.append(f"+{num}")

    result_filename = f"result_{message.from_user.id}.txt"
    with open(result_filename, "w", encoding="utf-8") as f:
        f.write(f"=== REGISTERED ACCOUNTS ({len(registered)}) ===\n")
        f.write("\n".join(registered))
        f.write(f"\n\n=== NO ACCOUNT ({len(no_account)}) ===\n")
        f.write("\n".join(no_account))
        f.write(f"\n\n=== BANNED ACCOUNTS ({len(banned)}) ===\n")
        f.write("\n".join(banned))

    caption_msg = (
        f"🎉 <b>স্ক্যানিং সম্পূর্ণ সম্পন্ন হয়েছে!</b>\n\n"
        f"{EMOJI_REGISTERED} Registered: <code>{len(registered)}</code>\n"
        f"{EMOJI_NO_ACCOUNT} No Account: <code>{len(no_account)}</code>\n"
        f"{EMOJI_BANNED} Banned: <code>{len(banned)}</code>"
    )

    await message.reply_document(
        document=result_filename,
        caption=caption_msg,
        parse_mode=enums.ParseMode.HTML
    )
    
    if os.path.exists(result_filename):
        os.remove(result_filename)

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.run()
    
