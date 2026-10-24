import os
import requests
import html
import threading
import time
import re
from datetime import datetime, timedelta
from flask import Flask
from pymongo import MongoClient
from decimal import Decimal, InvalidOperation
from bson.decimal128 import Decimal128

# Language Detector Function with expanded shortcodes mapping & fix
def detect_language(text):
    if not text:
        return "OTHERS"
    
    clean_text = text.lower().strip()
    
    # Direct shortcode matching
    if clean_text in ['en', 'eng', 'english', 'us', 'gb', 'ca']:
        return "EN"
    elif clean_text in ['bn', 'ben', 'bengali']:
        return "BN"
    elif clean_text in ['hi', 'hin', 'hindi']:
        return "HI"
    elif clean_text in ['ar', 'arabic']:
        return "AR"
    elif clean_text in ['ru', 'russian']:
        return "RU"
    elif clean_text in ['zh', 'chinese', 'cn']:
        return "ZH"
    elif clean_text in ['es', 'spanish']:
        return "ES"
    elif clean_text in ['fr', 'french']:
        return "FR"

    # Regex character range checks
    if re.search(r'[\u4e00-\u9fff]', text):
        return "ZH"
    elif re.search(r'[\u0600-\u06FF]', text):
        return "AR"
    elif re.search(r'[\u0400-\u04FF]', text):
        return "RU"
    elif re.search(r'[\u0900-\u097F]', text):
        return "HI"
    elif re.search(r'[a-zA-Z]', text):
        return "EN"
    return "OTHERS"

# Flask app initialization for Render Port Binding
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running perfectly with MongoDB!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# Environment Variables
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0")) if os.environ.get("ADMIN_ID") else 0
SUPPORT_USERNAME = os.environ.get("SUPPORT_USERNAME", "telegram")
OTP_GROUP_ID = os.environ.get("OTP_GROUP_ID", "")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "telegram_canada_otp_bot")

BASE_URL = f"https://api.telegram.org/bot{TOKEN}/"

# MongoDB Database Connection
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB_NAME]

users_col = db["users"]
stock_col = db["stock"]
vpn_stock_col = db["vpn_stock"]
vpn_orders_col = db["vpn_orders"]
orders_col = db["active_orders"]
settings_col = db["settings"]
user_states_col = db["user_states"]
refund_logs_col = db["refund_logs"]

# Helper functions for MongoDB User States
def get_user_state(user_id):
    doc = user_states_col.find_one({"user_id": user_id})
    return doc.get("state") if doc else None

def set_user_state(user_id, state):
    user_states_col.update_one({"user_id": user_id}, {"$set": {"state": state}}, upsert=True)

def delete_user_state(user_id):
    user_states_col.delete_one({"user_id": user_id})

# Default Settings Setup
def init_settings():
    if not settings_col.find_one({"key": "number_price"}):
        settings_col.insert_one({"key": "number_price", "value": "0.10"})
    if not settings_col.find_one({"key": "nord_price"}):
        settings_col.insert_one({"key": "nord_price", "value": "1.00"})
    if not settings_col.find_one({"key": "datama_price"}):
        settings_col.insert_one({"key": "datama_price", "value": "1.00"})
    if not settings_col.find_one({"key": "force_channels"}):
        settings_col.insert_one({"key": "force_channels", "channels": []})
    if not settings_col.find_one({"key": "bot_status"}):
        settings_col.insert_one({"key": "bot_status", "value": "ON"})

def migrate_money_fields_to_decimal128():
    try:
        for u in users_col.find({}, {"_id": 1, "balance": 1, "total_recharge": 1}):
            updates = {}
            for field in ("balance", "total_recharge"):
                value = u.get(field, 0)
                if not hasattr(value, "to_decimal"):
                    updates[field] = Decimal128(to_decimal(value))
            if updates:
                users_col.update_one({"_id": u["_id"]}, {"$set": updates})

        for r in refund_logs_col.find({}, {"_id": 1, "amount": 1}):
            value = r.get("amount", 0)
            if not hasattr(value, "to_decimal"):
                refund_logs_col.update_one(
                    {"_id": r["_id"]},
                    {"$set": {"amount": Decimal128(to_decimal(value))}}
                )
    except Exception as e:
        print(f"Decimal128 migration warning: {e}")

init_settings()
migrate_money_fields_to_decimal128()

BINANCE_PAY_ID = "907194603"

# Helper Functions
def mask_phone_number(phone):
    clean_phone = phone.strip()
    if len(clean_phone) > 6:
        mid = len(clean_phone) // 2
        return clean_phone[:mid-1] + "RX" + clean_phone[mid+1:]
    return clean_phone

def get_bot_status():
    doc = settings_col.find_one({"key": "bot_status"})
    return doc["value"] if doc else "ON"

def set_bot_status(status):
    settings_col.update_one({"key": "bot_status"}, {"$set": {"value": status}}, upsert=True)

def to_decimal(value):
    try:
        if value is None:
            return Decimal("0")
        if hasattr(value, "to_decimal"):
            return value.to_decimal()
        if isinstance(value, float):
            return Decimal(str(round(value, 12)))
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")

def format_money_exact(value):
    d = to_decimal(value)
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s if s else "0"

def format_number_price(price):
    return format_money_exact(price)

def get_number_price():
    doc = settings_col.find_one({"key": "number_price"})
    return to_decimal(doc["value"]) if doc else Decimal("0.10")

def set_number_price(new_price):
    price = to_decimal(new_price)
    if price < 0 or not price.is_finite():
        raise ValueError("Invalid price")
    settings_col.update_one(
        {"key": "number_price"},
        {"$set": {"value": format_money_exact(price)}},
        upsert=True
    )

def get_vpn_price(service):
    key = "nord_price" if service == "nord" else "datama_price"
    doc = settings_col.find_one({"key": key})
    return float(doc["value"]) if doc else 1.00

def set_vpn_price(service, new_price):
    key = "nord_price" if service == "nord" else "datama_price"
    settings_col.update_one({"key": key}, {"$set": {"value": str(new_price)}}, upsert=True)

def get_force_channels():
    doc = settings_col.find_one({"key": "force_channels"})
    return doc.get("channels", []) if doc else []

def set_force_channels(channels_list):
    settings_col.update_one({"key": "force_channels"}, {"$set": {"channels": channels_list}}, upsert=True)

def get_all_users_info():
    users = list(users_col.find())
    return [(u["user_id"], u.get("username", "NoUsername"), u.get("balance", 0.0)) for u in users]

def get_all_users():
    users = list(users_col.find({}, {"user_id": 1}))
    return [u["user_id"] for u in users if "user_id" in u]

def get_all_stock():
    stocks = list(stock_col.find())
    return [(str(s["_id"]), s["phone_number"], s["otp_link"]) for s in stocks]

def clear_all_stock():
    stock_col.delete_many({})

def add_vpn_stock_item(service, account_data):
    vpn_stock_col.insert_one({"service": service, "account": account_data})

def get_vpn_stock_count(service):
    return vpn_stock_col.count_documents({"service": service})

def save_vpn_order(user_id, service, amount):
    now_str = datetime.now().strftime("%d-%b-%Y %I:%M %p")
    res = vpn_orders_col.insert_one({
        "user_id": user_id,
        "service": service,
        "amount": amount,
        "status": "PENDING",
        "date": now_str
    })
    return str(res.inserted_id)

def get_user(user_id):
    u = users_col.find_one({"user_id": user_id})
    if u:
        return (u["user_id"], u.get("username", "NoUsername"), u.get("balance", 0.0), u.get("total_recharge", 0.0))
    return None

def add_user(user_id, username):
    users_col.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {"balance": Decimal128(Decimal("0")), "total_recharge": Decimal128(Decimal("0"))}, "$set": {"username": username}},
        upsert=True
    )

def update_balance(user_id, amount_usd):
    amount = to_decimal(amount_usd)
    users_col.update_one(
        {"user_id": user_id},
        {"$inc": {
            "balance": Decimal128(amount),
            "total_recharge": Decimal128(amount)
        }}
    )

def deduct_balance(user_id, amount_usd):
    amount = to_decimal(amount_usd)
    result = users_col.update_one(
        {"user_id": user_id, "balance": {"$gte": Decimal128(amount)}},
        {"$inc": {"balance": Decimal128(-amount)}}
    )
    return result.modified_count == 1

def add_stock_item(phone, link):
    stock_col.insert_one({"phone_number": phone, "otp_link": link})

def pop_stock_item():
    item = stock_col.find_one_and_delete({})
    if item:
        return item["phone_number"], item["otp_link"]
    return None, None

def delete_active_order(order_id):
    try:
        if order_id is not None:
            orders_col.delete_one({"_id": order_id})
    except Exception as e:
        print(f"Order rollback error: {e}")

def save_active_order(user_id, phone, link):
    now_str = datetime.now().strftime("%d-%b-%Y %I:%M %p")
    result = orders_col.insert_one({
        "user_id": user_id,
        "phone_number": phone,
        "otp_link": link,
        "otp_code": None,
        "app_type": None,
        "lang": None,
        "purchase_date": now_str,
        "created_at": datetime.now()
    })
    return result.inserted_id

def update_order_otp(phone, otp_code, app_type="WA", lang="EN"):
    latest_order = orders_col.find_one({"phone_number": phone}, sort=[("_id", -1)])
    if not latest_order:
        return

    orders_col.update_one(
        {"_id": latest_order["_id"]},
        {"$set": {"otp_code": otp_code, "app_type": app_type, "lang": lang}}
    )

def get_user_orders_all(user_id):
    rows = list(orders_col.find({"user_id": user_id}).sort("_id", -1))
    all_orders = []
    for row in rows:
        all_orders.append((
            row["phone_number"], 
            row.get("otp_code"), 
            row.get("purchase_date", "N/A"), 
            row.get("otp_link", ""), 
            row.get("app_type", "WA"), 
            row.get("lang", "EN")
        ))
    return all_orders

def get_order_by_phone(phone):
    row = orders_col.find_one({"phone_number": phone}, sort=[("_id", -1)])
    if row:
        return (str(row["_id"]), row["user_id"], row["otp_link"])
    return None

# Telegram API Requests
def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        return requests.post(BASE_URL + "sendMessage", json=payload, timeout=10).json()
    except Exception as e:
        print(f"Error sending message: {e}")
        return {}

def edit_message(chat_id, message_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        return requests.post(BASE_URL + "editMessageText", json=payload, timeout=10).json()
    except Exception as e:
        print(f"Error editing message: {e}")
        return {}

def send_photo_to_admin(chat_id, photo_file_id, caption, reply_markup=None):
    payload = {"chat_id": chat_id, "photo": photo_file_id, "caption": caption, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(BASE_URL + "sendPhoto", json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending photo: {e}")

def check_channel_member(user_id, channel_input):
    try:
        ch = channel_input.strip()
        if "t.me/" in ch:
            path = ch.split("t.me/")[-1].replace("/", "")
            if path.startswith("+") or path.startswith("joinchat"):
                ch = path 
            else:
                ch = "@" + path
        elif not ch.startswith("@") and not ch.startswith("-100"):
            ch = "@" + ch

        res = requests.post(BASE_URL + "getChatMember", json={"chat_id": ch, "user_id": user_id}, timeout=5).json()
        if res.get("ok"):
            status = res["result"]["status"]
            return status in ["creator", "administrator", "member"]
    except Exception as e:
        print(f"Check channel error: {e}")
    return False

def verify_force_join(user_id):
    channels = get_force_channels()
    if not channels:
        return True, []
    not_joined = []
    for ch in channels:
        if not check_channel_member(user_id, ch):
            not_joined.append(ch)
    return len(not_joined) == 0, not_joined

# Keyboards
def get_main_keyboard(is_admin=False):
    kb = [
        [
            {"text": "🛒 BUY NUMBER", "style": "success"},
            {"text": "🛡️ BUY VPN / IP", "style": "primary"}
        ],
        [
            {"text": "💳 DEPOSIT", "style": "primary"},
            {"text": "👤 PROFILE", "style": "primary"}
        ],
        [
            {"text": "🎧 SUPPORT", "style": "primary"}
        ]
    ]
    if is_admin:
        kb.append([{"text": "⚙️ ADMIN PANEL", "style": "danger"}])
    return {"keyboard": kb, "resize_keyboard": True}

def get_back_keyboard():
    kb = [[{"text": "⬅️ Back", "style": "danger"}]]
    return {"keyboard": kb, "resize_keyboard": True}

def get_admin_panel_data():
    bot_active = (get_bot_status() == "ON")
    current_price = get_number_price()
    nord_pr = get_vpn_price("nord")
    datama_pr = get_vpn_price("datama")
    chans = get_force_channels()
    chan_str = ", ".join(chans) if chans else "None"
    status_str = "🟢 ONLINE" if bot_active else "🔴 OFF / MAINTENANCE"
    
    msg = (
        "<b>⚙️ ADMIN PANEL</b>\n\n"
        f"🤖 <b>Bot Status:</b> {status_str}\n"
        f"🇨🇦 <b>Canada WhatsApp Price:</b> ${format_number_price(current_price)} USD\n"
        f"🛡️ <b>NordVPN Price:</b> ${nord_pr:.2f} USD | <b>DatamaPlus IP Price:</b> ${datama_pr:.2f} USD\n"
        f"📢 <b>Force Channels (Max 2):</b> {chan_str}"
    )
    
    toggle_btn = {"text": "🔴 Turn OFF Bot", "callback_data": "admin_toggle_bot_off", "style": "danger"} if bot_active else {"text": "🟢 Turn ON Bot", "callback_data": "admin_toggle_bot_on", "style": "success"}

    markup = {
        "inline_keyboard": [
            [toggle_btn],
            [{"text": "📊 DAILY STATS", "callback_data": "admin_daily_stats_1", "style": "success"}],
            [{"text": "➕ ADD BALANCE", "callback_data": "admin_direct_add_balance", "style": "success"}],
            [{"text": "🏷️ Change Canada WhatsApp Price", "callback_data": "admin_set_rate", "style": "primary"}],
            [{"text": "🛡️ Set NordVPN Price", "callback_data": "admin_set_nord_price", "style": "primary"}, {"text": "🌐 Set DatamaPlus IP Price", "callback_data": "admin_set_datama_price", "style": "primary"}],
            [{"text": "📁 Upload VPN / IP Stock File", "callback_data": "admin_upload_vpn_file", "style": "success"}],
            [{"text": "📢 Dynamic Force Join (2 Channels)", "callback_data": "admin_set_channels", "style": "success"}],
            [{"text": "📢 Broadcast Message", "callback_data": "admin_broadcast", "style": "primary"}],
            [{"text": "📁 Upload Number Stock File", "callback_data": "admin_upload_file", "style": "success"}],
            [{"text": "📊 View Current Stock", "callback_data": "admin_view_stock", "style": "primary"}],
            [{"text": "🗑️ Delete All Stock", "callback_data": "admin_delete_stock_confirm", "style": "danger"}]
        ]
    }
    return msg, markup

def render_daily_stats_page(page=1, items_per_page=10):
    users = list(users_col.find())
    total_users = len(users)
    if total_users == 0:
        return "❌ <b>কোনো ইউজার পাওয়া যায়নি!</b>", {"inline_keyboard": [[{"text": "⬅️ Back", "callback_data": "admin_panel_back"}]]}

    total_pages = (total_users + items_per_page - 1) // items_per_page
    if page < 1: page = 1
    if page > total_pages: page = total_pages

    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    page_users = users[start_idx:end_idx]

    stats_msg = f"📊 <b>DAILY USER STATS (Page {page}/{total_pages})</b>\n\n"

    for idx, u in enumerate(page_users, start=start_idx + 1):
        uid = u.get("user_id")
        uname = u.get("username", "NoUsername")
        bal = format_money_exact(u.get("balance", 0.0))
        
        user_orders = get_user_orders_all(uid)
        total_bought = len(user_orders)
        otp_received = sum(1 for o in user_orders if o[1])

        stats_msg += (
            f"<b>{idx}. User:</b> @{uname} (<code>{uid}</code>)\n"
            f"   💰 <b>Balance:</b> ${bal} USD\n"
            f"   🛒 <b>Bought:</b> {total_bought} | ✅ <b>OTP Received:</b> {otp_received}\n\n"
        )

    nav_buttons = []
    if total_pages > 1:
        row = []
        if page > 1:
            row.append({"text": f"◀️ Page {page-1}", "callback_data": f"admin_daily_stats_{page-1}", "style": "primary"})
        row.append({"text": f"📄 {page}/{total_pages}", "callback_data": "noop"})
        if page < total_pages:
            row.append({"text": f"Page {page+1} ▶️", "callback_data": f"admin_daily_stats_{page+1}", "style": "primary"})
        nav_buttons.append(row)

    nav_buttons.append([{"text": "⬅️ Back to Admin Panel", "callback_data": "admin_panel_back", "style": "danger"}])

    return stats_msg, {"inline_keyboard": nav_buttons}

def handle_update(update):
    try:
        msg_data = update.get("message") or update.get("callback_query", {}).get("message")
        if msg_data:
            chat_type = msg_data.get("chat", {}).get("type", "")
            if chat_type in ["group", "supergroup"]:
                return

        if "message" in update:
            msg = update["message"]
            chat_id = msg["chat"]["id"]
            user_id = msg["from"]["id"]
            username = msg["from"].get("username", "NoUsername")
            first_name = msg["from"].get("first_name", "User")
            text = msg.get("text", "")

            add_user(user_id, username)
            is_admin = (user_id == ADMIN_ID)
            current_price = get_number_price()
            bot_active = (get_bot_status() == "ON")

            if is_admin and "reply_to_message" in msg:
                reply_msg = msg["reply_to_message"]
                reply_text = reply_msg.get("text", "")
                if "VPN / IP ORDER #" in reply_text:
                    user_match = re.search(r'User ID: (\d+)', reply_text)
                    if user_match:
                        target_u_id = int(user_match.group(1))
                        vpn_account_info = text.strip()
                        
                        send_message(
                            target_u_id, 
                            f"🎉 <b>Your order is completed!</b>\n\n<b>Details:</b>\n<code>{vpn_account_info}</code>"
                        )
                        send_message(chat_id, f"✅ <b>Order notification successfully sent to User {target_u_id}!</b>")
                        return

            if text in ["⬅️ Back", "🔙 Back"]:
                delete_user_state(user_id)
                send_message(chat_id, "<b>মূল মেনুতে ফিরে আসা হয়েছে:</b>", reply_markup=get_main_keyboard(is_admin))
                return

            if not is_admin and not bot_active:
                send_message(chat_id, "⚠️ <b>সাময়িক সময়ের জন্য বট আপডেট করা হচ্ছে!</b>\nআপনারা একটু ধৈর্য ধরুন, এরপর জানিয়ে দেওয়া হবে। আপাতত কেউ ডিপোজিট বা নম্বর ক্রয় করবেন না। 🛑")
                return

            if not is_admin:
                is_joined, missing = verify_force_join(user_id)
                if not is_joined:
                    buttons = []
                    for idx, ch in enumerate(missing, 1):
                        clean_ch = ch.strip()
                        if clean_ch.startswith("http://") or clean_ch.startswith("https://"):
                            link = clean_ch
                        elif "t.me/" in clean_ch:
                            link = clean_ch if clean_ch.startswith("http") else f"https://{clean_ch}"
                        else:
                            link = f"https://t.me/{clean_ch.replace('@', '')}"
                        
                        buttons.append([{"text": f"📢 Join Channel {idx}", "url": link}])
                    
                    buttons.append([{"text": "🔄 Verify Join", "callback_data": "verify_join"}])
                    
                    send_message(
                        chat_id, 
                        "⚠️ <b>বটটি ব্যবহার করতে নিচের ২টি চ্যানেলে জয়েন করুন:</b>\nসবগুলো চ্যানেলে জয়েন করার পর Verify Join বোতামে চাপ দিন।", 
                        reply_markup={"inline_keyboard": buttons}
                    )
                    return

            state_data = get_user_state(user_id)
            if state_data:
                if is_admin and state_data in ["ADMIN_SET_NORD_PRICE", "ADMIN_SET_DATAMA_PRICE"]:
                    service = "nord" if state_data == "ADMIN_SET_NORD_PRICE" else "datama"
                    service_name = "NordVPN" if service == "nord" else "DatamaPlus IP"
                    try:
                        new_p = float(text)
                        set_vpn_price(service, new_p)
                        send_message(chat_id, f"✅ <b>{service_name} Price updated to: ${new_p:.2f} USD</b>", reply_markup=get_main_keyboard(is_admin))
                    except ValueError:
                        send_message(chat_id, "❌ <b>ভুল ইনপুট!</b> সঠিক সংখ্যা লিখুন (যেমন: 1.50)।")
                    delete_user_state(user_id)
                    return

                if is_admin and isinstance(state_data, dict) and state_data.get("step") == "ADMIN_UPLOAD_VPN_FILE":
                    service = state_data.get("service")
                    service_name = "NordVPN" if service == "nord" else "DatamaPlus IP"
                    if "document" in msg:
                        doc = msg["document"]
                        file_name = doc.get("file_name", "").lower()
                        if not (file_name.endswith(".txt") or file_name.endswith(".csv")):
                            send_message(chat_id, "❌ <b>দয়া করে শুধুমাত্র .txt অথবা .csv ফাইল আপলোড করুন!</b>", reply_markup=get_back_keyboard())
                            return

                        file_id = doc["file_id"]
                        file_info = requests.get(BASE_URL + f"getFile?file_id={file_id}").json()
                        if file_info.get("ok"):
                            file_path = file_info["result"]["file_path"]
                            content = requests.get(f"https://api.telegram.org/file/bot{TOKEN}/{file_path}").text
                            
                            count = 0
                            for line in content.splitlines():
                                line = line.strip()
                                if line and ":" in line:
                                    add_vpn_stock_item(service, line)
                                    count += 1
                            
                            send_message(chat_id, f"✅ <b>সফলভাবে {count} টি {service_name} ডাটা স্টকে আপলোড করা হয়েছে!</b>", reply_markup=get_main_keyboard(is_admin))
                            delete_user_state(user_id)
                            return
                    else:
                        send_message(chat_id, "❌ <b>অনুগ্রহ করে একটি সঠিক টেক্সট (.txt / .csv) ফাইল আপলোড করুন।</b>", reply_markup=get_back_keyboard())
                        return

                if isinstance(state_data, str) and state_data == "BUY_MULTI_QTY":
                    try:
                        qty = int(text.strip())
                        if qty <= 0:
                            send_message(chat_id, "❌ <b>সঠিক সংখ্যা লিখুন (কমপক্ষে ১ টি)।</b>")
                            return

                        if qty > 20:
                            send_message(chat_id, "❌ <b>একসাথে সর্বোচ্চ ২০টি নম্বর কিনতে পারবেন।</b>")
                            delete_user_state(user_id)
                            return

                        u_info = get_user(user_id)
                        bal = u_info[2] if u_info else 0.0
                        total_cost = to_decimal(current_price) * Decimal(qty)

                        if to_decimal(bal) < to_decimal(total_cost):
                            send_message(
                                chat_id,
                                f"❌ <b>পর্যাপ্ত ব্যালেন্স নেই!</b>\n"
                                f"{qty} টি নম্বর কিনতে ${format_number_price(total_cost)} USD লাগবে। "
                                f"আপনার ব্যালেন্স: ${format_money_exact(bal)} USD।"
                            )
                            delete_user_state(user_id)
                            return

                        stock_items = get_all_stock()
                        if len(stock_items) < qty:
                            send_message(
                                chat_id,
                                f"⚠️ <b>দুঃখিত! স্টকে পর্যাপ্ত নম্বর নেই।</b>\n"
                                f"বর্তমানে স্টকে {len(stock_items)} টি নম্বর খালি রয়েছে।"
                            )
                            delete_user_state(user_id)
                            return

                        purchased_list = []

                        try:
                            for _ in range(qty):
                                phone, link = pop_stock_item()
                                if not phone:
                                    raise RuntimeError("Stock empty")

                                order_id = save_active_order(user_id, phone, link)
                                purchased_list.append((phone, link, order_id))

                        except Exception as e:
                            for p, l, oid in purchased_list:
                                add_stock_item(p, l)
                                delete_active_order(oid)
                            delete_user_state(user_id)
                            send_message(chat_id, "⚠️ <b>নম্বর অর্ডার তৈরি করতে সমস্যা হয়েছে।</b> ব্যালেন্স কাটা হয়নি।")
                            return

                        res_msg = f"✅ <b>সফলভাবে {len(purchased_list)} টি Canada নম্বর কেনা হয়েছে!</b>\n\n"
                        for idx, (p, l, oid) in enumerate(purchased_list, 1):
                            res_msg += f"<b>{idx}.</b> 📱 <code>{html.escape(str(p))}</code> | 🔗 {html.escape(str(l))}\n"

                        res_msg += f"\n💰 <b>মোট ফি কাটা হবে:</b> ${format_number_price(total_cost)} USD\n👉 OTP পেতে <b>Check OTP</b> চাপুন।"

                        multi_btns = []
                        for p, l, oid in purchased_list[:10]:
                            multi_btns.append([{"text": f"🔄 Check OTP ({p})", "callback_data": f"chk_otp_{p}", "style": "primary"}])

                        delivery_result = send_message(chat_id, res_msg, reply_markup={"inline_keyboard": multi_btns})

                        if not delivery_result.get("ok"):
                            for p, l, oid in purchased_list:
                                add_stock_item(p, l)
                                delete_active_order(oid)

                            delete_user_state(user_id)
                            send_message(chat_id, "⚠️ <b>নম্বর পাঠাতে সমস্যা হয়েছে।</b> ব্যালেন্স কাটা হয়নি।")
                            return

                        if not deduct_balance(user_id, total_cost):
                            for p, l, oid in purchased_list:
                                add_stock_item(p, l)
                                delete_active_order(oid)
                            delete_user_state(user_id)
                            send_message(chat_id, "⚠️ <b>পেমেন্ট প্রসেস করতে সমস্যা হয়েছে।</b>")
                            return

                        delete_user_state(user_id)
                        send_message(chat_id, "<b>মূল মেনু:</b>", reply_markup=get_main_keyboard(is_admin))
                        return

                    except ValueError:
                        send_message(chat_id, "❌ <b>ভুল ইনপুট!</b> কেবল পূর্ণসংখ্যা লিখুন (যেমন: 2, 5, 10)।")
                        return

                if is_admin and state_data == "ADMIN_SET_PRICE":
                    try:
                        price_text = text.strip()
                        new_pr = to_decimal(price_text)
                        if new_pr < 0:
                            raise ValueError
                        set_number_price(new_pr)
                        send_message(chat_id, f"✅ <b>Canada হোয়াটসঅ্যাপ নম্বরের নতুন মূল্য সেট করা হয়েছে: ${format_number_price(new_pr)} USD</b>", reply_markup=get_main_keyboard(is_admin))
                    except ValueError:
                        send_message(chat_id, "❌ <b>ভুল ইনপুট!</b> সঠিক সংখ্যা লিখুন (যেমন: 0.125)।")
                    delete_user_state(user_id)
                    return

                if is_admin and state_data == "ADMIN_DIRECT_ADD_BAL":
                    try:
                        parts = text.split()
                        if len(parts) < 2:
                            send_message(chat_id, "❌ <b>সঠিক ফরম্যাটে দিন:</b> <code>USER_ID AMOUNT</code>\nউদাহরণ: <code>123456789 5.00</code>")
                            return
                        
                        target_u_id = int(parts[0].strip())
                        usd_val = to_decimal(parts[1].strip())
                        
                        update_balance(target_u_id, usd_val)
                        send_message(chat_id, f"✅ <b>User ID {target_u_id}-কে ${format_money_exact(usd_val)} USD ব্যালেন্স যোগ করে দেওয়া হয়েছে!</b>", reply_markup=get_main_keyboard(is_admin))
                        send_message(target_u_id, f"🎉 <b>এডমিন আপনার অ্যাকাউন্টে ${format_money_exact(usd_val)} USD যোগ করেছেন!</b>")
                    except Exception as e:
                        send_message(chat_id, "❌ <b>ভুল ইনপুট!</b>\nউদাহরণ: <code>123456789 5.00</code>")
                    delete_user_state(user_id)
                    return

                if is_admin and state_data == "ADMIN_SET_CHANNELS":
                    ch_list = [c.strip() for c in text.split(",") if c.strip()]
                    if len(ch_list) > 2:
                        send_message(chat_id, "❌ <b>সর্বোচ্চ ২টি চ্যানেল লিঙ্ক বা ইউজারনেম দিতে পারবেন!</b>")
                        return
                    set_force_channels(ch_list)
                    send_message(chat_id, f"✅ <b>ফোর্স জয়েন চ্যানেল ২ টি সেট করা হয়েছে!</b>\nচ্যানেলসমূহ: {', '.join(ch_list)}", reply_markup=get_main_keyboard(is_admin))
                    delete_user_state(user_id)
                    return

                if isinstance(state_data, dict) and state_data.get("step") == "WAITING_AMOUNT":
                    try:
                        amount = float(text)
                        if amount <= 0:
                            send_message(chat_id, "❌ <b>সঠিক পরিমাণ উল্লেখ করুন!</b>")
                            return
                        
                        set_user_state(user_id, {"step": "WAITING_TRX", "amount": amount})

                        msg_text = (
                            f"🟡 <b>Binance Pay (Crypto)</b>\n\n"
                            f"💵 <b>ডিপোজিট পরিমাণ:</b> {amount:.2f} USDT\n"
                            f"🆔 <b>Binance Pay ID:</b> <code>{BINANCE_PAY_ID}</code>\n\n"
                            f"উপরের আইডি তে USDT পাঠানোর পর আপনার <b>Binance Order ID / TrxID</b> মেসেজ লিখে পাঠান:"
                        )

                        send_message(chat_id, msg_text, reply_markup=get_back_keyboard())
                        return
                    except ValueError:
                        send_message(chat_id, "❌ <b>ভুল ইনপুট!</b> কেবল সংখ্যা লিখুন। (যেমন: 5 বা 10)")
                        return

                elif isinstance(state_data, dict) and state_data.get("step") == "WAITING_TRX":
                    set_user_state(user_id, {
                        "step": "WAITING_SCREENSHOT",
                        "amount": state_data["amount"],
                        "trx_id": text
                    })
                    send_message(chat_id, "📸 <b>ধন্যবাদ! এবার পেমেন্টের একটি স্পষ্ট স্ক্রিনশট (Photo) পাঠান:</b>", reply_markup=get_back_keyboard())
                    return

                elif isinstance(state_data, dict) and state_data.get("step") == "WAITING_SCREENSHOT":
                    if "photo" in msg:
                        photo_file_id = msg["photo"][-1]["file_id"]
                        amount = state_data["amount"]
                        trx_id = state_data["trx_id"]

                        converted_usd = amount
                        usd_str_clean = f"{converted_usd:.2f}"
                        admin_markup = {
                            "inline_keyboard": [
                                [
                                    {"text": f"✅ Auto Approve (${converted_usd:.2f})", "callback_data": f"appusd_{user_id}_{usd_str_clean}", "style": "success"},
                                    {"text": "✏️ Custom Amount", "callback_data": f"dep_app_{user_id}", "style": "primary"}
                                ],
                                [{"text": "❌ Reject Request", "callback_data": f"dep_rej_{user_id}", "style": "danger"}]
                            ]
                        }
                        admin_caption = (
                            f"📥 <b>New Binance Deposit Request</b>\n\n"
                            f"👤 <b>User:</b> {html.escape(first_name)} (@{username})\n"
                            f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
                            f"💰 <b>Payment:</b> {amount:.2f} USDT\n"
                            f"🧾 <b>Order ID / TrxID:</b> <code>{html.escape(trx_id)}</code>\n\n"
                            f"যাচাই করে ডলারে যোগ করতে নিচের বাটন প্রেস করুন:"
                        )
                        
                        send_photo_to_admin(ADMIN_ID, photo_file_id, admin_caption, reply_markup=admin_markup)
                        send_message(chat_id, "✅ <b>আপনার তথ্য ও স্ক্রিনশট অ্যাডমিনের কাছে পাঠানো হয়েছে!</b>\nযাচাই করার পর অ্যাকাউন্টে ডলার ব্যালেন্স যোগ করা হবে।", reply_markup=get_main_keyboard(is_admin))
                        delete_user_state(user_id)
                        return
                    else:
                        send_message(chat_id, "❌ <b>অনুগ্রহ করে পেমেন্টের একটি ছবি/স্ক্রিনশট পাঠান।</b>", reply_markup=get_back_keyboard())
                        return

                elif is_admin and state_data == "ADMIN_UPLOAD_FILE":
                    if "document" in msg:
                        doc = msg["document"]
                        file_name = doc.get("file_name", "").lower()
                        if not (file_name.endswith(".txt") or file_name.endswith(".csv")):
                            send_message(chat_id, "❌ <b>দয়া করে শুধুমাত্র .txt অথবা .csv ফাইল আপলোড করুন!</b>", reply_markup=get_back_keyboard())
                            return

                        file_id = doc["file_id"]
                        file_info = requests.get(BASE_URL + f"getFile?file_id={file_id}").json()
                        if file_info.get("ok"):
                            file_path = file_info["result"]["file_path"]
                            content = requests.get(f"https://api.telegram.org/file/bot{TOKEN}/{file_path}").text
                            
                            count = 0
                            for line in content.splitlines():
                                line = line.strip()
                                if line.startswith("+") and ("http://" in line or "https://" in line):
                                    parts = line.replace(",", " ").split()
                                    if len(parts) >= 2:
                                        add_stock_item(parts[0].strip(), parts[1].strip())
                                        count += 1
                            
                            send_message(chat_id, f"✅ <b>সফলভাবে {count} টি Canada নম্বর স্টকে আপলোড করা হয়েছে!</b>", reply_markup=get_main_keyboard(is_admin))
                            delete_user_state(user_id)
                            return
                    else:
                        send_message(chat_id, "❌ <b>অনুগ্রহ করে একটি সঠিক টেক্সট (.txt / .csv) ফাইল আপলোড করুন।</b>", reply_markup=get_back_keyboard())
                        return

                elif isinstance(state_data, str) and state_data.startswith("ADMIN_APPROVE_AMOUNT_"):
                    target_user = int(state_data.replace("ADMIN_APPROVE_AMOUNT_", ""))
                    try:
                        usd_val = to_decimal(text.strip())
                        update_balance(target_user, usd_val)
                        send_message(chat_id, f"✅ <b>User ID {target_user}-কে ${format_money_exact(usd_val)} USD ব্যালেন্স যোগ করা হয়েছে।</b>")
                        send_message(target_user, f"🎉 <b>আপনার ডিপোজিট প্রসেস সফল হয়েছে! ${format_money_exact(usd_val)} USD অ্যাকাউন্টে যোগ করা হয়েছে।</b>")
                    except Exception:
                        send_message(chat_id, "❌ <b>ভুল অ্যামাউন্ট!</b> কেবল সংখ্যা লিখুন।")
                    delete_user_state(user_id)
                    return

                elif isinstance(state_data, str) and state_data == "ADMIN_BROADCAST":
                    all_users = get_all_users()
                    success, failed = 0, 0
                    send_message(chat_id, f"⏳ <b>{len(all_users)} জন ইউজারের কাছে মেসেজ পাঠানো শুরু হচ্ছে...</b>")
                    for u_id in all_users:
                        try:
                            res = send_message(u_id, text)
                            if res.get("ok"):
                                success += 1
                            else:
                                failed += 1
                        except Exception:
                            failed += 1
                    send_message(chat_id, f"✅ <b>ব্রডকাস্ট সম্পন্ন হয়েছে!</b>\n\n🎯 সফল: {success}\n❌ ব্যর্থ: {failed}", reply_markup=get_main_keyboard(is_admin))
                    delete_user_state(user_id)
                    return

            if text == "/start":
                welcome_text = f"👋 <b>Welcome {html.escape(first_name)}!</b>\n\nনিচের মেনু থেকে সার্ভিস সিলেক্ট করুন:"
                send_message(chat_id, welcome_text, reply_markup=get_main_keyboard(is_admin))

            elif text in ["🛒 BUY NUMBER", "📱 GET NUMBER"]:
                markup = {
                    "inline_keyboard": [
                        [{"text": f"🇨🇦 Buy Single Canada Number (${format_number_price(current_price)})", "callback_data": "confirm_buy_canada", "style": "success"}],
                        [{"text": "🔢 Buy Multiple Numbers", "callback_data": "buy_multi_num", "style": "primary"}]
                    ]
                }
                send_message(chat_id, f"<b>Canada WhatsApp Service Selected:</b>\n\nমূল্য: <b>${format_number_price(current_price)} USD / Number</b>\n⚠️ <i>No refund | Number validity 20 days</i>", reply_markup=get_back_keyboard())
                send_message(chat_id, "সার্ভিস অপশন বেছে নিন:", reply_markup=markup)

            elif text == "🛡️ BUY VPN / IP":
                nord_pr = get_vpn_price("nord")
                datama_pr = get_vpn_price("datama")
                markup = {
                    "inline_keyboard": [
                        [{"text": f"🛡️ NordVPN (${nord_pr:.2f})", "callback_data": "buy_vpn_nord", "style": "primary"}],
                        [{"text": f"🌐 DatamaPlus IP (${datama_pr:.2f})", "callback_data": "buy_vpn_datama", "style": "primary"}]
                    ]
                }
                send_message(chat_id, "🛡️ <b>Select Service:</b>\n\nপছন্দের VPN / IP সার্ভিস বেছে নিন:", reply_markup=get_back_keyboard())
                send_message(chat_id, "উপলব্ধ সার্ভিসসমূহ:", reply_markup=markup)

            elif text == "💳 DEPOSIT":
                dep_text = f"💳 <b>Binance Deposit Options</b>\n\nআপনার সুবিধাজনক Binance Crypto পেমেন্ট বাটন প্রেস করুন:"
                markup = {
                    "inline_keyboard": [
                        [{"text": "🟡 Binance Pay (USDT)", "callback_data": "dep_binance", "style": "success"}]
                    ]
                }
                send_message(chat_id, dep_text, reply_markup=get_back_keyboard())
                send_message(chat_id, "পেমেন্ট গেটওয়ে:", reply_markup=markup)

            elif text == "👤 PROFILE":
                u_info = get_user(user_id)
                bal = u_info[2] if u_info else 0.0
                tot = u_info[3] if u_info else 0.0
                all_purchased = len(get_user_orders_all(user_id))
                prof_text = (
                    f"👤 <b>Your Profile Information</b>\n\n"
                    f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
                    f"💰 <b>Current Balance:</b> ${format_money_exact(bal)} USD\n"
                    f"📊 <b>Total Recharge:</b> ${format_money_exact(tot)} USD\n"
                    f"🛒 <b>Total Purchased Numbers:</b> {all_purchased} টি"
                )
                send_message(chat_id, prof_text, reply_markup=get_back_keyboard())

            elif text == "🎧 SUPPORT":
                send_message(chat_id, f"<b>যেকোনো সাহায্যে যোগাযোগ করুন:</b>\n👉 @{SUPPORT_USERNAME}", reply_markup=get_back_keyboard())

            elif text == "⚙️ ADMIN PANEL" and is_admin:
                admin_msg, admin_markup = get_admin_panel_data()
                send_message(chat_id, admin_msg, reply_markup=get_back_keyboard())
                send_message(chat_id, "এডমিন একশন সিলেক্ট করুন:", reply_markup=admin_markup)

        elif "callback_query" in update:
            cb = update["callback_query"]
            cb_id = cb["id"]
            chat_id = cb["message"]["chat"]["id"]
            message_id = cb["message"]["message_id"]
            user_id = cb["from"]["id"]
            data = cb.get("data", "")
            is_admin = (user_id == ADMIN_ID)
            bot_active = (get_bot_status() == "ON")

            try:
                requests.post(BASE_URL + "answerCallbackQuery", json={"callback_query_id": cb_id}, timeout=5)
            except Exception:
                pass

            if not is_admin and not bot_active and data != "verify_join":
                send_message(chat_id, "⚠️ <b>সাময়িক সময়ের জন্য বট বন্ধ রয়েছে!</b>")
                return

            current_price = get_number_price()

            if data == "noop":
                return

            if data.startswith("buy_vpn_"):
                service = "nord" if "nord" in data else "datama"
                service_title = "NordVPN" if service == "nord" else "DatamaPlus IP"
                pr = get_vpn_price(service)
                u_info = get_user(user_id)
                bal = u_info[2] if u_info else 0.0

                if to_decimal(bal) < to_decimal(pr):
                    edit_message(chat_id, message_id, f"❌ <b>পর্যাপ্ত ব্যালেন্স নেই!</b>\n{service_title} কিনতে ${pr:.2f} USD লাগবে। আপনার ব্যালেন্স: ${format_money_exact(bal)} USD।")
                    return

                conf_markup = {
                    "inline_keyboard": [
                        [
                            {"text": "✅ Confirm Order", "callback_data": f"conf_vpn_{service}", "style": "success"},
                            {"text": "❌ Cancel", "callback_data": "cancel_vpn", "style": "danger"}
                        ]
                    ]
                }
                edit_message(chat_id, message_id, f"🛡️ <b>{service_title} Order Confirmation</b>\n\n💰 Price: <b>${pr:.2f} USD</b>\n💵 Your Balance: <b>${bal:.2f} USD</b>\n\nআপনি কি এই অর্ডারটি করতে চান?", reply_markup=conf_markup)
                return

            elif data.startswith("conf_vpn_"):
                service = "nord" if "nord" in data else "datama"
                service_title = "NordVPN" if service == "nord" else "DatamaPlus IP"
                pr = get_vpn_price(service)
                u_info = get_user(user_id)
                bal = u_info[2] if u_info else 0.0

                if to_decimal(bal) < to_decimal(pr):
                    edit_message(chat_id, message_id, f"❌ <b>পর্যাপ্ত ব্যালেন্স নেই!</b>\n{service_title} কিনতে ${pr:.2f} USD লাগবে।")
                    return

                deduct_balance(user_id, pr)
                order_id = save_vpn_order(user_id, service, pr)

                admin_notif = (
                    f"🚨 <b>NEW VPN / IP ORDER #{order_id}</b>\n\n"
                    f"👤 <b>User ID:</b> <code>{user_id}</code>\n"
                    f"🛡️ <b>Service:</b> {service_title}\n"
                    f"💰 <b>Price:</b> ${pr:.2f} USD\n\n"
                    f"👉 <i>এই মেসেজটিতে Reply দিয়ে তথ্য পাঠাতে পারেন।</i>"
                )
                send_message(ADMIN_ID, admin_notif)

                edit_message(chat_id, message_id, f"✅ <b>আপনার {service_title} অর্ডারটি সফলভাবে কনফার্ম হয়েছে!</b>\n\n💰 ফি কাটা হয়েছে: ${pr:.2f} USD\n⏳ অল্প কিছুক্ষণের মধ্যে অ্যাডমিন এটি ডেলিভারি দিয়ে দেবে।")
                return

            elif data == "cancel_vpn":
                edit_message(chat_id, message_id, "❌ <b>অর্ডারটি বাতিল করা হয়েছে।</b>")
                return

            if data == "admin_toggle_bot_off" and is_admin:
                set_bot_status("OFF")
                admin_msg, admin_markup = get_admin_panel_data()
                edit_message(chat_id, message_id, admin_msg, reply_markup=admin_markup)

            elif data == "admin_toggle_bot_on" and is_admin:
                set_bot_status("ON")
                admin_msg, admin_markup = get_admin_panel_data()
                edit_message(chat_id, message_id, admin_msg, reply_markup=admin_markup)

            elif data == "verify_join":
                is_joined, _ = verify_force_join(user_id)
                if is_joined:
                    send_message(chat_id, "✅ <b>ধন্যবাদ! ভেরিফিকেশন সফল হয়েছে।</b>\nএখন বট ব্যবহার করতে পারবেন।", reply_markup=get_main_keyboard(is_admin))
                else:
                    send_message(chat_id, "❌ <b>আপনি এখনও সবগুলো চ্যানেলে জয়েন করেননি!</b>")

            elif data == "buy_multi_num":
                set_user_state(user_id, "BUY_MULTI_QTY")
                send_message(chat_id, "🔢 <b>কতগুলো Canada নম্বর কিনতে চান লিখে পাঠান:</b>\n(যেমন: 2, 5, 10 ইত্যাদি)", reply_markup=get_back_keyboard())

            elif data == "confirm_buy_canada":
                u_info = get_user(user_id)
                bal = u_info[2] if u_info else 0.0

                if to_decimal(bal) < to_decimal(current_price):
                    edit_message(chat_id, message_id, f"❌ <b>পর্যাপ্ত ব্যালেন্স নেই!</b>\nনম্বর কিনতে অন্তত ${format_number_price(current_price)} USD ব্যালেন্স লাগবে। Deposit সেকশন থেকে রিচার্জ করুন।")
                    return

                phone, link = pop_stock_item()
                if not phone:
                    edit_message(chat_id, message_id, "⚠️ <b>দুঃখিত! বর্তমানে স্টক ফাঁকা রয়েছে।</b> কিছু সময় পর আবার চেষ্টা করুন।")
                    return

                markup = {
                    "inline_keyboard": [
                        [{"text": "🔄 Check OTP", "callback_data": f"chk_otp_{phone}", "style": "primary"}],
                        [{"text": "🛒 Buy Another Number", "callback_data": "confirm_buy_canada", "style": "success"}]
                    ]
                }
                res_text = (
                    f"✅ <b>নম্বর বরাদ্দ করা হয়েছে!</b>\n\n"
                    f"🇨🇦 <b>Canada Number:</b> <code>{html.escape(str(phone))}</code>\n"
                    f"🔗 <b>OTP Link:</b> {link}\n"
                    f"💰 <b>ফি কাটা হয়েছে:</b> ${format_number_price(current_price)} USD\n\n"
                    f"👉 নম্বরটি অ্যাপে ব্যবহার করার পর <b>Check OTP</b> বাটনে চাপ দিন।"
                )

                try:
                    order_id = save_active_order(user_id, phone, link)
                    if order_id is None:
                        raise RuntimeError("Could not create purchase order.")
                except Exception as e:
                    add_stock_item(phone, link)
                    edit_message(chat_id, message_id, "⚠️ <b>অর্ডার তৈরি করতে সমস্যা হয়েছে।</b>")
                    return

                delivery_result = send_message(chat_id, res_text, reply_markup=markup)
                if not delivery_result.get("ok"):
                    add_stock_item(phone, link)
                    delete_active_order(order_id)
                    edit_message(chat_id, message_id, "⚠️ <b>নম্বর পাঠাতে সমস্যা হয়েছে।</b>")
                    return

                if not deduct_balance(user_id, current_price):
                    add_stock_item(phone, link)
                    delete_active_order(order_id)
                    edit_message(chat_id, message_id, "⚠️ <b>পেমেন্ট প্রসেস করতে সমস্যা হয়েছে।</b>")
                    return

                send_message(chat_id, "<b>মূল মেনু:</b>", reply_markup=get_main_keyboard(is_admin))

            elif data.startswith("chk_otp_"):
                phone = data.replace("chk_otp_", "")
                order = get_order_by_phone(phone)
                
                if order:
                    link = order[2] # নির্দিষ্ট নম্বরের নিজস্ব ইউনিক লিংক
                    otp_code = None
                    raw_response_text = ""
                    
                    try:
                        headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                            "Accept": "*/*",
                            "Cache-Control": "no-cache"
                        }

                        # নির্দিষ্ট নম্বরের লিংকে রিকোয়েস্ট পাঠানো হচ্ছে
                        response = requests.get(link, headers=headers, timeout=8)
                        api_text = response.text.strip()
                        raw_response_text = api_text

                        if re.match(r'^\d{3,10}$', api_text):
                            otp_code = api_text
                        else:
                            matches = re.findall(r'\b\d{6}\b', response.text)
                            clean_phone = re.sub(r'\D', '', phone)
                            
                            for code in matches:
                                if code not in ['111111', '000000', '123456'] and code not in clean_phone:
                                    otp_code = code
                                    break

                    except Exception as e:
                        print(f"OTP Scraping Error: {e}")

                    if otp_code:
                        app_type = "WB" if ("business" in raw_response_text.lower() or "smb" in raw_response_text.lower()) else "WA"
                        detected_lang = detect_language(raw_response_text)

                        update_order_otp(phone, otp_code, app_type=app_type, lang=detected_lang)
                        
                        markup = {
                            "inline_keyboard": [
                                [{"text": "🛒 Buy Another Number", "callback_data": "confirm_buy_canada", "style": "success"}]
                            ]
                        }
                        
                        otp_msg = (
                            f"<b>Your WhatsApp Code ({app_type})</b>\n\n"
                            f"🔑 <b>OTP:</b> <code>{otp_code}</code>\n"
                            f"🌐 <b>Language:</b> <code>[{detected_lang}]</code>"
                        )
                        send_message(chat_id, otp_msg, reply_markup=markup)
                        
                        if OTP_GROUP_ID:
                            masked_num = mask_phone_number(phone)
                            group_msg = (
                                f"🎉 <b>New OTP Received! ({app_type})</b>\n\n"
                                f"📱 <b>Number:</b> <code>{masked_num}</code>\n"
                                f"🔑 <b>OTP Code:</b> <code>{otp_code}</code>\n"
                                f"🌐 <b>Language:</b> <code>[{detected_lang}]</code>"
                            )
                            send_message(OTP_GROUP_ID, group_msg)
                    else:
                        send_message(chat_id, "⌛ <b>OTP এখনও আসেনি!</b> অনুগ্রহ করে কিছুক্ষণ পর আবার Check OTP চাপুন।")

            elif data == "admin_panel_back" and is_admin:
                admin_msg, admin_markup = get_admin_panel_data()
                edit_message(chat_id, message_id, admin_msg, reply_markup=admin_markup)

            elif data.startswith("admin_daily_stats_") and is_admin:
                page_num = int(data.replace("admin_daily_stats_", ""))
                s_msg, s_markup = render_daily_stats_page(page=page_num)
                edit_message(chat_id, message_id, s_msg, reply_markup=s_markup)

            elif data == "admin_direct_add_balance" and is_admin:
                set_user_state(user_id, "ADMIN_DIRECT_ADD_BAL")
                send_message(
                    chat_id,
                    "➕ <b>যেকোনো ইউজারের ব্যালেন্স যোগ করতে User ID ও Amount লিখে পাঠান:</b>\n\n"
                    "ফরম্যাট: <code>USER_ID AMOUNT</code>\n"
                    "উদাহরণ: <code>123456789 5.00</code>",
                    reply_markup=get_back_keyboard()
                )

            elif data == "admin_set_nord_price" and is_admin:
                set_user_state(user_id, "ADMIN_SET_NORD_PRICE")
                send_message(chat_id, "🛡️ <b>NordVPN-এর নতুন মূল্য ($ USD) লিখে পাঠান:</b>", reply_markup=get_back_keyboard())

            elif data == "admin_set_datama_price" and is_admin:
                set_user_state(user_id, "ADMIN_SET_DATAMA_PRICE")
                send_message(chat_id, "🌐 <b>DatamaPlus IP-এর নতুন মূল্য ($ USD) লিখে পাঠান:</b>", reply_markup=get_back_keyboard())

            elif data == "admin_upload_vpn_file" and is_admin:
                markup = {
                    "inline_keyboard": [
                        [{"text": "🛡️ Upload NordVPN", "callback_data": "up_vpn_nord", "style": "primary"}],
                        [{"text": "🌐 Upload DatamaPlus IP", "callback_data": "up_vpn_datama", "style": "primary"}]
                    ]
                }
                send_message(chat_id, "কোন স্টক ফাইল আপলোড করবেন সিলেক্ট করুন:", reply_markup=markup)

            elif data.startswith("up_vpn_") and is_admin:
                service = "nord" if "nord" in data else "datama"
                service_name = "NordVPN" if service == "nord" else "DatamaPlus IP"
                set_user_state(user_id, {"step": "ADMIN_UPLOAD_VPN_FILE", "service": service})
                send_message(chat_id, f"📁 <b>{service_name} ফাইলটি (.txt / .csv) পাঠান:</b>\nফরম্যাট:\n<code>email:password</code> বা <code>ip:port:user:pass</code>", reply_markup=get_back_keyboard())

            elif data == "admin_set_channels" and is_admin:
                set_user_state(user_id, "ADMIN_SET_CHANNELS")
                send_message(chat_id, "📢 <b>ফোর্স জয়েন চ্যানেল ২ টি লিঙ্ক বা ইউজারনেম দিন:</b>", reply_markup=get_back_keyboard())

            elif data == "dep_binance":
                set_user_state(user_id, {"step": "WAITING_AMOUNT"})
                send_message(chat_id, "🟡 <b>Binance Deposit Selected</b>\n\nকত <b>USDT</b> (USD) ডিপোজিট করতে চান লিখে পাঠান:", reply_markup=get_back_keyboard())

            elif data == "admin_set_rate" and is_admin:
                set_user_state(user_id, "ADMIN_SET_PRICE")
                send_message(chat_id, f"🏷️ <b>Canada WhatsApp নম্বরের নতুন মূল্য ($ USD) লিখে পাঠান:</b>\n(বর্তমান রেট: ${format_number_price(current_price)} USD)", reply_markup=get_back_keyboard())

            elif data == "admin_broadcast" and is_admin:
                set_user_state(user_id, "ADMIN_BROADCAST")
                send_message(chat_id, "📢 <b>সব ইউজারদের উদ্দেশ্যে পাঠানোর বার্তাটি লিখে পাঠান:</b>", reply_markup=get_back_keyboard())

            elif data == "admin_upload_file" and is_admin:
                set_user_state(user_id, "ADMIN_UPLOAD_FILE")
                send_message(chat_id, "📁 <b>Canada নম্বর সম্বলিত ফাইলটি (.txt / .csv) এখানে পাঠাও:</b>\nফরম্যাট:\n<code>+1234567890, https://sms.elitetrick.com/record/index.php?key=...</code>", reply_markup=get_back_keyboard())

            elif data == "admin_view_stock" and is_admin:
                stock_items = get_all_stock()
                nord_count = get_vpn_stock_count("nord")
                datama_count = get_vpn_stock_count("datama")
                
                stock_text = (
                    f"📊 <b>বর্তমান স্টক ওভারভিউ:</b>\n\n"
                    f"🇨🇦 <b>Canada Number Stock:</b> {len(stock_items)} টি\n"
                    f"🛡️ <b>NordVPN Stock:</b> {nord_count} টি\n"
                    f"🌐 <b>DatamaPlus IP Stock:</b> {datama_count} টি\n\n"
                )
                
                if stock_items:
                    stock_text += "<b>Canada নম্বরসমূহ:</b>\n"
                    for item in stock_items[:20]:
                        stock_text += f"📱 <code>{item[1]}</code>\n🔗 {item[2]}\n\n"
                    if len(stock_items) > 20:
                        stock_text += f"<i>...এবং আরও {len(stock_items) - 20} টি নম্বর রয়েছে।</i>"
                
                send_message(chat_id, stock_text)

            elif data == "admin_delete_stock_confirm" and is_admin:
                markup = {"inline_keyboard": [[{"text": "✅ Yes, Delete All", "callback_data": "admin_delete_stock_execute", "style": "danger"}]]}
                edit_message(chat_id, message_id, "⚠️ <b>আপনি কি নিশ্চিতভাবে সমস্ত স্টক ফাইল/নম্বর মুছে ফেলতে চান?</b>", reply_markup=markup)

            elif data == "admin_delete_stock_execute" and is_admin:
                clear_all_stock()
                edit_message(chat_id, message_id, "🗑️ <b>সফলভাবে সমস্ত স্টকে থাকা নম্বর ডিলিট করা হয়েছে!</b>")

            elif data.startswith("appusd_") and is_admin:
                parts = data.split("_")
                target_user = int(parts[1])
                usd_val = float(parts[2])
                update_balance(target_user, usd_val)
                send_message(chat_id, f"✅ <b>User ID {target_user}-এর অ্যাকাউন্টে সফলভাবে ${usd_val:.2f} USD যোগ করা হয়েছে!</b>")
                send_message(target_user, f"🎉 <b>আপনার ডিপোজিট প্রসেস সফল হয়েছে! ${format_money_exact(usd_val)} USD অ্যাকাউন্টে যোগ করা হয়েছে।</b>")

            elif data.startswith("dep_app_") and is_admin:
                target_user = int(data.replace("dep_app_", ""))
                set_user_state(user_id, f"ADMIN_APPROVE_AMOUNT_{target_user}")
                send_message(chat_id, f"<b>User ID {target_user}-এর অ্যাকাউন্টে কত $ (USD) যোগ করতে চান লিখে পাঠান:</b>")

            elif data.startswith("dep_rej_") and is_admin:
                target_user = int(data.replace("dep_rej_", ""))
                send_message(target_user, f"❌ <b>আপনার জমা দেওয়া ডিপোজিট প্রুফটি সঠিক নয়!</b>\nসাপোর্ট অ্যাডমিনের সাথে কথা বলুন: @{SUPPORT_USERNAME}")
                send_message(chat_id, f"❌ <b>User ID {target_user}-এর ডিপোজিট বাতিল করা হয়েছে।</b>")

    except Exception as general_error:
        print(f"General Exception Prevented Crash: {general_error}")

def safe_execution_wrapper(upd):
    try:
        handle_update(upd)
    except Exception as e:
        print(f"Exception Handled Safety: {e}")

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()

    print("🚀 Canada OTP Bot Engine Online...")
    offset = 0
    while True:
        try:
            res = requests.get(BASE_URL + "getUpdates", params={"offset": offset, "timeout": 20}, timeout=25).json()
            if res.get("ok"):
                for update in res.get("result", []):
                    offset = update["update_id"] + 1
                    # Python-এর আধুনিক থ্রেডিং স্ট্যান্ডার্ড অনুযায়ী daemon=True ব্যবহার করা হয়েছে
                    threading.Thread(target=safe_execution_wrapper, args=(update,), daemon=True).start()
        except Exception as e:
            print(f"Polling Network Recovering... {e}")
            time.sleep(3)
