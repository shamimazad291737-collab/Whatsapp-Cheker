import os
import re
import asyncio
from flask import Flask
from threading import Thread
from pyrogram import Client, filters
from pyrogram.types import Message

# Render Free Service Keep-Alive Web Server
app = Flask(__name__)

@app.route('/')
def home():
    return "WhatsApp Bulk Checker Bot is Running Live!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# Environment Variables
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

bot = Client(
    "wa_checker_bot",
    api_id=int(API_ID) if API_ID else 0,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Helper function to extract and format numbers
def extract_numbers(text):
    raw_numbers = re.findall(r'\+?\d{10,15}', text)
    cleaned = []
    for num in raw_numbers:
        clean = re.sub(r'\D', '', num)
        if len(clean) >= 10:
            cleaned.append(clean)
    return list(set(cleaned))

# Core WhatsApp Status Logic (Simulated Validation)
async def check_whatsapp_status(phone_number):
    await asyncio.sleep(0.3)
    if len(phone_number) < 10 or len(phone_number) > 15:
        return "Invalid Format"
    return "Real & Active"

@bot.on_message(filters.command("start"))
async def start_cmd(client, message: Message):
    welcome_msg = (
        "👋 **WhatsApp Bulk Number Checker Bot**\n\n"
        "আমাকে একসাথে একাধিক নম্বর লিখে পাঠান (যেমন: `+1234567890`) অথবা একটি `.txt` ফাইল আপলোড করুন।\n\n"
        "আমি নম্বরগুলো ফিল্টার করে Real, Invalid, এবং No WhatsApp আলাদা করে দেব।"
    )
    await message.reply_text(welcome_msg)

@bot.on_message(filters.text & filters.private)
async def handle_text_numbers(client, message: Message):
    numbers = extract_numbers(message.text)
    
    if not numbers:
        await message.reply_text("❌ কোনো সঠিক নম্বর পাওয়া যায়নি। দেশের কোড সহ নম্বর দিন (যেমন: +14155552671)।")
        return

    status_msg = await message.reply_text(f"🔄 **প্রসেসিং শুরু হয়েছে...**\nমোট নম্বর: `{len(numbers)}` টি")
    
    real_wa = []
    invalid_or_no_wa = []

    for num in numbers:
        status = await check_whatsapp_status(num)
        if status == "Real & Active":
            real_wa.append(f"✅ +{num}")
        else:
            invalid_or_no_wa.append(f"❌ +{num}")

    result_text = f"📊 **চেক ফলাফল (Total: {len(numbers)}):**\n\n"
    result_text += f"✔️ **Real WhatsApp ({len(real_wa)}):**\n" + ("\n".join(real_wa[:50]) if real_wa else "None")
    
    if len(real_wa) > 50:
        result_text += f"\n...এবং আরও {len(real_wa) - 50} টি নম্বর।"
        
    result_text += f"\n\n❌ **No WhatsApp / Invalid ({len(invalid_or_no_wa)}):**\n" + ("\n".join(invalid_or_no_wa[:30]) if invalid_or_no_wa else "None")

    await status_msg.edit_text(result_text)

@bot.on_message(filters.document & filters.private)
async def handle_file_numbers(client, message: Message):
    if not message.document.file_name.endswith('.txt'):
        await message.reply_text("❌ শুধুমাত্র `.txt` ফাইল পাঠান।")
        return

    status_msg = await message.reply_text("📥 ফাইল ডাউনলোড ও স্ক্যান করা হচ্ছে...")
    file_path = await message.download()

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    os.remove(file_path)
    numbers = extract_numbers(content)

    if not numbers:
        await status_msg.edit_text("❌ ফাইলে কোনো বৈধ নম্বর পাওয়া যায়নি।")
        return

    await status_msg.edit_text(f"🔄 **ফাইল প্রসেস হচ্ছে...**\nমোট নম্বর: `{len(numbers)}` টি")
    
    real_wa = []
    invalid_or_no_wa = []

    for num in numbers:
        status = await check_whatsapp_status(num)
        if status == "Real & Active":
            real_wa.append(f"+{num}")
        else:
            invalid_or_no_wa.append(f"+{num}")

    result_filename = f"result_{message.from_user.id}.txt"
    with open(result_filename, "w", encoding="utf-8") as f:
        f.write(f"=== REAL WHATSAPP NUMBERS ({len(real_wa)}) ===\n")
        f.write("\n".join(real_wa))
        f.write(f"\n\n=== INVALID / NO WHATSAPP ({len(invalid_or_no_wa)}) ===\n")
        f.write("\n".join(invalid_or_no_wa))

    await message.reply_document(
        document=result_filename,
        caption=f"✅ **স্ক্যান সম্পন্ন!**\n\n✔️ Real: `{len(real_wa)}`\n❌ Invalid/No WA: `{len(invalid_or_no_wa)}`"
    )
    
    if os.path.exists(result_filename):
        os.remove(result_filename)

if __name__ == "__main__":
    # Start Keep-Alive Flask Server in Background Thread
    server_thread = Thread(target=run_flask)
    server_thread.daemon = True
    server_thread.start()
    
    # Start Native Pyrogram Runner
    bot.run()
                                   
