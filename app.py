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

# Environment Variables & Multi-Admin Support
TOKEN = os.environ.get("BOT_TOKEN")
admin_env = os.environ.get("ADMIN_ID", "0")
ADMIN_IDS = [int(aid.strip()) for aid in admin_env.split(",") if aid.strip().isdigit()] if admin_env else [0]

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
daily_stats_col = db["daily_stats"]

def is_user_admin(user_id):
    return user_id in ADMIN_IDS

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
        settings_col.insert_one({"key": "number_price", "value": "0.135"})
    if not settings_col.find_one({"key": "cost_price"}):
        settings_col.insert_one({"key": "cost_price", "value": "0.10"})
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
    except Exception as e:
        print(f"Decimal128 migration warning: {e}")

init_settings()
migrate_money_fields_to_decimal128()

# Binance Pay ID
BINANCE_PAY_ID = "1289098351"

# Daily Statistics Trackers (Deposit & Profit with Midnight Reset)
def get_today_date_str():
    return datetime.now().strftime("%Y-%m-%d")

def record_deposit_stat(amount_usd):
    date_str = get_today_date_str()
    amt = to_decimal(amount_usd)
    daily_stats_col.update_one(
        {"date": date_str},
        {"$inc": {"total_deposit": Decimal128(amt)}},
        upsert=True
    )

def record_sale_stat(qty, sell_price, cost_price):
    date_str = get_today_date_str()
    revenue = to_decimal(sell_price) * Decimal(qty)
    cost = to_decimal(cost_price) * Decimal(qty)
    profit = revenue - cost
    
    daily_stats_col.update_one(
        {"date": date_str},
        {
            "$inc": {
                "total_sold": qty,
                "total_revenue": Decimal128(revenue),
                "total_profit": Decimal128(profit)
            }
        },
        upsert=True
    )

def get_daily_stat(date_str):
    doc = daily_stats_col.find_one({"date": date_str})
    if not doc:
        return {"total_deposit": Decimal("0"), "total_sold": 0, "total_revenue": Decimal("0"), "total_profit": Decimal("0")}
    return {
        "total_deposit": to_decimal(doc.get("total_deposit", 0)),
        "total_sold": doc.get("total_sold", 0),
        "total_revenue": to_decimal(doc.get("total_revenue", 0)),
        "total_profit": to_decimal(doc.get("total_profit", 0))
    }

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

def get_number_price():
    doc = settings_col.find_one({"key": "number_price"})
    return to_decimal(doc["value"]) if doc else Decimal("0.135")

def get_cost_price():
    doc = settings_col.find_one({"key": "cost_price"})
    return to_decimal(doc["value"]) if doc else Decimal("0.10")

def set_number_price(new_price):
    price = to_decimal(new_price)
    settings_col.update_one({"key": "number_price"}, {"$set": {"value": format_money_exact(price)}}, upsert=True)

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

def get_all_users():
    users = list(users_col.find({}, {"user_id": 1}))
    return [u["user_id"] for u in users if "user_id" in u]

def get_all_stock():
    return [(str(s["_id"]), s["phone_number"], s["otp_link"]) for s in stock_col.find()]

def clear_all_stock():
    stock_col.delete_many({})

def add_vpn_stock_item(service, account_data):
    vpn_stock_col.insert_one({"service": service, "account": account_data})

def get_vpn_stock_count(service):
    return vpn_stock_col.count_documents({"service": service})

def save_vpn_order(user_id, service, amount):
    now_str = datetime.now().strftime("%d-%b-%Y %I:%M %p")
    res = vpn_orders_col.insert_one({"user_id": user_id, "service": service, "amount": amount, "status": "PENDING", "date": now_str})
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
        {"$inc": {"balance": Decimal128(amount), "total_recharge": Decimal128(amount)}}
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
        if order_id:
            orders_col.delete_one({"_id": order_id})
    except Exception as e:
        print(f"Order rollback error: {e}")

def save_active_order(user_id, phone, link):
    now_str = datetime.now().strftime("%d-%b-%Y %I:%M %p")
    result = orders_col.insert_one({
        "user_id": user_id, "phone_number": phone, "otp_link": link,
        "otp_code": None, "app_type": None, "lang": None,
        "purchase_date": now_str, "created_at": datetime.now()
    })
    return result.inserted_id

def update_order_otp(phone, otp_code, app_type="WA", lang="EN"):
    latest_order = orders_col.find_one({"phone_number": phone}, sort=[("_id", -1)])
    if latest_order:
        orders_col.update_one({"_id": latest_order["_id"]}, {"$set": {"otp_code": otp_code, "app_type": app_type, "lang": lang}})

def get_user_orders_all(user_id):
    rows = list(orders_col.find({"user_id": user_id}).sort("_id", -1))
    return [(row["phone_number"], row.get("otp_code"), row.get("purchase_date", "N/A"), row.get("otp_link", ""), row.get("app_type", "WA"), row.get("lang", "EN")) for row in rows]

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

def edit_caption(chat_id, message_id, caption, reply_markup=None):
    payload = {"chat_id": chat_id, "message_id": message_id, "caption": caption, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        return requests.post(BASE_URL + "editMessageCaption", json=payload, timeout=10).json()
    except Exception as e:
        print(f"Error editing caption: {e}")
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
            ch = path if (path.startswith("+") or path.startswith("joinchat")) else "@" + path
        elif not ch.startswith("@") and not ch.startswith("-100"):
            if ch.lstrip("-").isdigit():
                ch = "-100" + ch if not ch.startswith("-100") else ch
            else:
                ch = "@" + ch

        res = requests.post(BASE_URL + "getChatMember", json={"chat_id": ch, "user_id": user_id}, timeout=5).json()
        if res.get("ok"):
            return res["result"]["status"] in ["creator", "administrator", "member"]
    except Exception as e:
        print(f"Check channel/group error: {e}")
    return False

def verify_force_join(user_id):
    channels = get_force_channels()
    if not channels:
        return True, []
    not_joined = [ch for ch in channels if not check_channel_member(user_id, ch)]
    return len(not_joined) == 0, not_joined

def get_chat_invite_link(chat_input):
    try:
        ch = channel_input.strip()
        if "t.me/" in ch:
            return ch if ch.startswith("http") else "https://" + ch
        
        if not ch.startswith("@") and not ch.startswith("-100"):
            if ch.lstrip("-").isdigit():
                ch = "-100" + ch if not ch.startswith("-100") else ch
            else:
                ch = "@" + ch

        res = requests.post(BASE_URL + "getChat", json={"chat_id": ch}, timeout=5).json()
        if res.get("ok"):
            chat_data = res["result"]
            if "invite_link" in chat_data:
                return chat_data["invite_link"]
            elif "username" in chat_data:
                return f"https://t.me/{chat_data['username']}"
    except Exception as e:
        print(f"Get invite link error: {e}")
    
    if "t.me/" in channel_input:
        return channel_input if channel_input.startswith("http") else "https://" + channel_input
    clean_ch = channel_input.strip().replace("@", "")
    return f"https://t.me/{clean_ch}"

# Keyboards with Styled Premium Icons for Buttons
def get_main_keyboard(is_admin=False):
    kb = [
        [
            {"text": "🛒 𝗕𝗨𝗬 𝗡𝗨𝗠𝗕𝗘𝗥", "style": "success"},
            {"text": "🛡️ 𝗕𝗨𝗬 𝗩𝗣𝗡 / 𝗜𝗣", "style": "primary"}
        ],
        [
            {"text": "💳 𝗗𝗘𝗣𝗢𝗦𝗜𝗧", "style": "primary"},
            {"text": "👤 𝗣𝗥𝗢𝗙𝗜𝗟𝗘", "style": "primary"}
        ],
        [
            {"text": "🎧 𝗦𝗨𝗣𝗣𝗢𝗥𝗧", "style": "primary"}
        ]
    ]
    if is_admin:
        kb.append([{"text": "⚙️ 𝗔𝗗𝗠𝗜𝗡 𝗣𝗔𝗡𝗘𝗟", "style": "danger"}])
    return {"keyboard": kb, "resize_keyboard": True}

def get_back_keyboard():
    kb = [[{"text": "⬅️ 𝗕𝗮𝗰𝗸", "style": "danger"}]]
    return {"keyboard": kb, "resize_keyboard": True}

def get_admin_panel_data():
    bot_active = (get_bot_status() == "ON")
    current_price = get_number_price()
    nord_pr = get_vpn_price("nord")
    datama_pr = get_vpn_price("datama")
    chans = get_force_channels()
    chan_str = ", ".join(chans) if chans else "None"
    status_str = "🟢 𝗢𝗡𝗟𝗜𝗡𝗘" if bot_active else "🔴 𝗢𝗙𝗙 / 𝗠𝗔𝗜𝗡𝗧𝗘𝗡𝗔𝗡𝗖𝗘"
    
    today_stats = get_daily_stat(get_today_date_str())
    
    msg = (
        "<b>⚙️ 𝗔𝗗𝗠𝗜𝗡 𝗣𝗔𝗡𝗘𝗟</b>\n\n"
        f"🤖 <b>বট স্ট্যাটাস:</b> {status_str}\n"
        f"<tg-emoji emoji-id=\"5397916757333654639\">🇨🇦</tg-emoji> <b>কানাডা নম্বর বিক্রয় মূল্য:</b> <tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji>${format_money_exact(current_price)} USD\n"
        f"<tg-emoji emoji-id=\"5420155432272438703\">🛡️</tg-emoji> <b>NordVPN মূল্য:</b> <tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji>{nord_pr:.2f} USD | <b>DatamaPlus IP:</b> <tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji>{datama_pr:.2f} USD\n"
        f"📢 <b>ফোর্স জয়েন চ্যানেল/গ্রুপ:</b> {chan_str}\n\n"
        f"📈 <tg-emoji emoji-id=\"5264713049637409446\">📊</tg-emoji> <b>আজকের লাইভ পরিসংখ্যান ({get_today_date_str()}):</b>\n"
        f"<tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji> <b>মোট ডিপোজিট:</b> ${format_money_exact(today_stats['total_deposit'])} USDT\n"
        f"🛒 <b>নম্বর বিক্রয় হয়েছে:</b> {today_stats['total_sold']} টি\n"
        f"<tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji> <b>মোট রেভিনিউ:</b> ${format_money_exact(today_stats['total_revenue'])} USD\n"
        f"<tg-emoji emoji-id=\"5337267511261960341\">🔥</tg-emoji> <b>নেট প্রফিট:</b> ${format_money_exact(today_stats['total_profit'])} USD\n"
    )
    
    toggle_btn = {"text": "🔴 বট বন্ধ করুন", "callback_data": "admin_toggle_bot_off", "style": "danger"} if bot_active else {"text": "🟢 বট চালু করুন", "callback_data": "admin_toggle_bot_on", "style": "success"}

    markup = {
        "inline_keyboard": [
            [toggle_btn],
            [{"text": "📊 𝗗𝗔𝗜𝗟𝗬 𝗗𝗘𝗣𝗢𝗦𝗜𝗧 & 𝗣𝗥𝗢𝗙𝗜𝗧 𝗛𝗜𝗦𝗧𝗢𝗥𝗬", "callback_data": "admin_view_history", "style": "success"}],
            [{"text": "📊 𝗗𝗔𝗜𝗟𝗬 𝗨𝗦𝗘𝗥 𝗦𝗧𝗔𝗧𝗦", "callback_data": "admin_daily_stats_1", "style": "success"}],
            [{"text": "➕ 𝗔𝗗𝗗 𝗕𝗔𝗟𝗔𝗡𝗖𝗘", "callback_data": "admin_direct_add_balance", "style": "success"}],
            [{"text": "🏷️ 𝗖𝗵𝗮𝗻𝗴𝗲 𝗖𝗮𝗻𝗮𝗱𝗮 𝗣𝗿𝗶𝗰𝗲", "callback_data": "admin_set_rate", "style": "primary"}],
            [{"text": "🛡️ 𝗦𝗲𝘁 𝗡𝗼𝗿𝗱 𝗣𝗿𝗶𝗰𝗲", "callback_data": "admin_set_nord_price", "style": "primary"}, {"text": "🌐 𝗦𝗲𝘁 𝗗𝗮𝘁𝗮𝗺𝗮 𝗣𝗿𝗶𝗰𝗲", "callback_data": "admin_set_datama_price", "style": "primary"}],
            [{"text": "📁 𝗨𝗽𝗹𝗼𝗮𝗱 𝗩𝗣𝗡 𝗦𝘁𝗼𝗰𝗸", "callback_data": "admin_upload_vpn_file", "style": "success"}, {"text": "📢 𝗙𝗼𝗿𝗰𝗲 𝗝𝗼𝗶𝗻 (Group/Channel)", "callback_data": "admin_set_channels", "style": "success"}],
            [{"text": "📢 𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁 𝗠𝗲𝘀𝘀𝗮𝗴𝗲", "callback_data": "admin_broadcast", "style": "primary"}, {"text": "📁 𝗨𝗽𝗹𝗼𝗮𝗱 𝗡𝘂𝗺𝗯𝗲𝗿𝘀", "callback_data": "admin_upload_file", "style": "success"}],
            [{"text": "📊 𝗩𝗶𝗲𝘄 𝗦𝘁𝗼𝗰𝗸", "callback_data": "admin_view_stock", "style": "primary"}, {"text": "🗑️ 𝗖𝗹𝗲𝗮𝗿 𝗦𝘁𝗼𝗰𝗸", "callback_data": "admin_delete_stock_confirm", "style": "danger"}]
        ]
    }
    return msg, markup

def render_daily_stats_page(page=1, items_per_page=10):
    users = list(users_col.find())
    total_users = len(users)
    if total_users == 0:
        return "❌ <tg-emoji emoji-id=\"5217822164362739968\">❌</tg-emoji> <b>কোনো ইউজার পাওয়া যায়নি!</b>", {"inline_keyboard": [[{"text": "⬅️ 𝗕𝗮𝗰𝗸", "callback_data": "admin_panel_back"}]]}

    total_pages = (total_users + items_per_page - 1) // items_per_page
    if page < 1: page = 1
    if page > total_pages: page = total_pages

    page_users = users[(page - 1) * items_per_page : page * items_per_page]
    stats_msg = f"📊 <b>𝗗𝗔𝗜𝗟𝗬 𝗨𝗦𝗘𝗥 𝗦𝗧𝗔𝗧𝗦 (𝗣𝗮𝗴𝗲 {page}/{total_pages})</b>\n\n"

    for idx, u in enumerate(page_users, start=((page - 1) * items_per_page) + 1):
        uid = u.get("user_id")
        uname = u.get("username", "NoUsername")
        bal = format_money_exact(u.get("balance", 0.0))
        user_orders = get_user_orders_all(uid)
        stats_msg += f"<b>{idx}. @{uname}</b> (<code>{uid}</code>)\n   <tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji> <b>ব্যালেন্স:</b> ${bal} | 🛒 <b>ক্রয়:</b> {len(user_orders)} টি\n\n"

    nav_buttons = []
    if total_pages > 1:
        row = []
        if page > 1: row.append({"text": f"◀️ Page {page-1}", "callback_data": f"admin_daily_stats_{page-1}", "style": "primary"})
        row.append({"text": f"📄 {page}/{total_pages}", "callback_data": "noop"})
        if page < total_pages: row.append({"text": f"Page {page+1} ▶️", "callback_data": f"admin_daily_stats_{page+1}", "style": "primary"})
        nav_buttons.append(row)

    nav_buttons.append([{"text": "⬅️ 𝗕𝗮𝗰𝗸 𝘁𝗼 𝗔𝗱𝗺𝗶𝗻", "callback_data": "admin_panel_back", "style": "danger"}])
    return stats_msg, {"inline_keyboard": nav_buttons}

def handle_update(update):
    try:
        msg_data = update.get("message") or update.get("callback_query", {}).get("message")
        if msg_data and msg_data.get("chat", {}).get("type", "") in ["group", "supergroup"]:
            return

        if "message" in update:
            msg = update["message"]
            chat_id = msg["chat"]["id"]
            user_id = msg["from"]["id"]
            username = msg["from"].get("username", "NoUsername")
            first_name = msg["from"].get("first_name", "User")
            text = msg.get("text", "")

            add_user(user_id, username)
            is_admin = is_user_admin(user_id)
            current_price = get_number_price()
            bot_active = (get_bot_status() == "ON")

            if text in ["⬅️ 𝗕𝗮𝗰𝗸", "🔙 𝗕𝗮𝗰𝗸"]:
                delete_user_state(user_id)
                send_message(chat_id, "<b>🏠 মূল মেনুতে ফিরে আসা হয়েছে:</b>", reply_markup=get_main_keyboard(is_admin))
                return

            if is_admin and "reply_to_message" in msg:
                reply_text = msg["reply_to_message"].get("text", "")
                if "VPN / IP ORDER #" in reply_text:
                    user_match = re.search(r'User ID: (\d+)', reply_text)
                    if user_match:
                        send_message(int(user_match.group(1)), f"🎉 <b>আপনার অর্ডারটি সফলভাবে সম্পন্ন হয়েছে!</b>\n\n<b>বিবরণ:</b>\n<code>{text.strip()}</code>")
                        send_message(chat_id, f"<tg-emoji emoji-id=\"5841276284155467413\">✅</tg-emoji> <b>অর্ডার ডিটেইলস সফলভাবে ইউজারের কাছে পাঠানো হয়েছে!</b>")
                        return

            if not is_admin and not bot_active:
                send_message(chat_id, "⚠️ <b>সাময়িক সময়ের জন্য বট আপডেট করা হচ্ছে!</b> অনুগ্রহ করে একটু অপেক্ষা করুন।")
                return

            if not is_admin:
                is_joined, missing = verify_force_join(user_id)
                if not is_joined:
                    buttons = []
                    for i, ch in enumerate(missing):
                        link = get_chat_invite_link(ch)
                        buttons.append([{"text": f"📢 Join Group/Channel {i+1}", "url": link}])
                    buttons.append([{"text": "🔄 𝗩𝗲𝗿𝗶𝗳𝘆 𝗝𝗼𝗶𝗻", "callback_data": "verify_join"}])
                    send_message(chat_id, "⚠️ <b>বটটি ব্যবহার করতে নিচের গ্রুপ বা চ্যানেলগুলোতে অবশ্যই জয়েন করুন:</b>", reply_markup={"inline_keyboard": buttons})
                    return

            state_data = get_user_state(user_id)
            
            # Direct check for file upload even if state_data is set or lost
            if is_admin and "document" in msg:
                doc = msg["document"]
                file_id = doc["file_id"]
                file_info = requests.get(BASE_URL + f"getFile?file_id={file_id}").json()
                file_content = ""
                if file_info.get("ok"):
                    file_path = file_info["result"]["file_path"]
                    download_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
                    resp = requests.get(download_url)
                    file_content = resp.text

                lines = file_content.split("\n")
                count = 0
                for line in lines:
                    line_clean = line.strip()
                    if not line_clean:
                        continue
                    if "Phone Number" in line_clean or "Direct Link" in line_clean or "====" in line_clean or "VNUM" in line_clean or "Purchased" in line_clean or "Time:" in line_clean:
                        continue
                    
                    if "," in line_clean:
                        parts = [p.strip().strip('"').strip("'") for p in line_clean.split(",")]
                        if len(parts) >= 2:
                            phone = parts[0]
                            link = parts[1]
                            if phone and link and phone.startswith("+"):
                                add_stock_item(phone, link)
                                count += 1
                    elif "http" in line_clean:
                        for sep in ["----", "---", "--", " "]:
                            if sep in line_clean:
                                parts = line_clean.split(sep, 1)
                                phone = parts[0].strip()
                                link = parts[1].strip()
                                if phone and link and phone.startswith("+"):
                                    add_stock_item(phone, link)
                                    count += 1
                                break

                send_message(chat_id, f"<tg-emoji emoji-id=\"5841276284155467413\">✅</tg-emoji> সফলভাবে <b>{count}</b> টি নম্বর স্টক করা হয়েছে!", reply_markup=get_main_keyboard(is_admin))
                delete_user_state(user_id)
                return

            if state_data:
                if is_admin and isinstance(state_data, str) and state_data.startswith("ADMIN_SET_PRICE_CUSTOM"):
                    service = "nord" if "nord" in state_data else "datama"
                    try:
                        set_vpn_price(service, float(text.strip()))
                        send_message(chat_id, f"<tg-emoji emoji-id=\"5841276284155467413\">✅</tg-emoji> <b>{service.upper()}VPN মূল্য আপডেট করা হয়েছে!</b>", reply_markup=get_main_keyboard(is_admin))
                    except ValueError:
                        send_message(chat_id, "<tg-emoji emoji-id=\"5217822164362739968\">❌</tg-emoji> সঠিক পরিমাণ লিখুন।")
                    delete_user_state(user_id)
                    return

                if isinstance(state_data, str) and state_data == "BUY_MULTI_QTY":
                    try:
                        qty = int(text.strip())
                        if qty <= 0 or qty > 20:
                            send_message(chat_id, "<tg-emoji emoji-id=\"5217822164362739968\">❌</tg-emoji> <b>সর্বোচ্চ ২০টি এবং কমপক্ষে ১টি নম্বর কিনতে পারবেন।</b>", reply_markup={"inline_keyboard": [[{"text": "❌ Cancel", "callback_data": "cancel_multi_buy"}]]})
                            return

                        total_cost = current_price * Decimal(qty)
                        u_info = get_user(user_id)
                        bal = u_info[2] if u_info else 0.0

                        if to_decimal(bal) < total_cost:
                            send_message(chat_id, f"<tg-emoji emoji-id=\"5217822164362739968\">❌</tg-emoji> <b>অপর্যাপ্ত ব্যালেন্স!</b> প্রয়োজন: <tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji>${format_money_exact(total_cost)} USD", reply_markup={"inline_keyboard": [[{"text": "❌ Cancel", "callback_data": "cancel_multi_buy"}]]})
                            return

                        stock_items = get_all_stock()
                        if len(stock_items) < qty:
                            send_message(chat_id, f"⚠️ <b>স্টকে পর্যাপ্ত নম্বর নেই!</b> বর্তমানে খালি আছে: {len(stock_items)} টি", reply_markup={"inline_keyboard": [[{"text": "❌ Cancel", "callback_data": "cancel_multi_buy"}]]})
                            return

                        purchased_list = []
                        for _ in range(qty):
                            phone, link = pop_stock_item()
                            order_id = save_active_order(user_id, phone, link)
                            purchased_list.append((phone, link, order_id))

                        deduct_balance(user_id, total_cost)
                        record_sale_stat(qty, current_price, get_cost_price())

                        res_msg = f"<tg-emoji emoji-id=\"5841276284155467413\">✅</tg-emoji> <b>সফলভাবে {len(purchased_list)} টি নম্বর কেনা হয়েছে!</b>\n\n"
                        multi_btns = []
                        for idx, (p, l, oid) in enumerate(purchased_list, 1):
                            res_msg += f"<b>{idx}.</b> 📱 <code>{p}</code>\n{l}\n\n"
                            if idx <= 10:
                                multi_btns.append([{"text": f"🔄 Check OTP ({p})", "callback_data": f"chk_otp_{p}", "style": "primary"}])

                        send_message(chat_id, res_msg, reply_markup={"inline_keyboard": multi_btns})
                        delete_user_state(user_id)
                        send_message(chat_id, "<b>🏠 মূল মেনু:</b>", reply_markup=get_main_keyboard(is_admin))
                        return
                    except ValueError:
                        send_message(chat_id, "<tg-emoji emoji-id=\"5217822164362739968\">❌</tg-emoji> সঠিক সংখ্যা লিখুন।", reply_markup={"inline_keyboard": [[{"text": "❌ Cancel", "callback_data": "cancel_multi_buy"}]]})
                        return

                if is_admin and state_data == "ADMIN_SET_PRICE":
                    try:
                        set_number_price(to_decimal(text.strip()))
                        send_message(chat_id, f"<tg-emoji emoji-id=\"5841276284155467413\">✅</tg-emoji> <b>কানাডা নম্বরের মূল্য আপডেট করা হয়েছে!</b>", reply_markup=get_main_keyboard(is_admin))
                    except ValueError:
                        send_message(chat_id, "<tg-emoji emoji-id=\"5217822164362739968\">❌</tg-emoji> ভুল পরিমাণ।")
                    delete_user_state(user_id)
                    return

                if is_admin and isinstance(state_data, dict) and state_data.get("step") == "ADMIN_ADD_BAL_USER":
                    try:
                        target_user_id = int(text.strip())
                        set_user_state(user_id, {"step": "ADMIN_ADD_BAL_AMT", "target_user_id": target_user_id})
                        send_message(chat_id, f"💵 <b>ইউজার আইডি:</b> <code>{target_user_id}</code>\n\nএবার কত পরিমাণ ব্যালেন্স (USD/USDT) যোগ করতে চান সংখ্যা লিখে পাঠান (যেমন: <code>0.136</code> বা <code>5</code>):", reply_markup=get_back_keyboard())
                        return
                    except ValueError:
                        send_message(chat_id, "<tg-emoji emoji-id=\"5217822164362739968\">❌</tg-emoji> সঠিক ইউজার আইডি (সংখ্যা) লিখুন:")
                        return

                if is_admin and isinstance(state_data, dict) and state_data.get("step") == "ADMIN_ADD_BAL_AMT":
                    try:
                        add_amt = to_decimal(text.strip())
                        if add_amt <= 0:
                            raise ValueError
                        target_user_id = state_data["target_user_id"]
                        
                        update_balance(target_user_id, add_amt)
                        record_deposit_stat(add_amt)
                        
                        send_message(chat_id, f"<tg-emoji emoji-id=\"5841276284155467413\">✅</tg-emoji> <b>সফলভাবে ${format_money_exact(add_amt)} ব্যালেন্স ইউজার (<code>{target_user_id}</code>) এর অ্যাকাউন্টে যোগ করা হয়েছে এবং ডিপোজিট স্ট্যাটাসে রেকর্ড হয়েছে!</b>", reply_markup=get_main_keyboard(is_admin))
                        send_message(target_user_id, f"🎉 <b>এডমিন আপনার অ্যাকাউন্টে ব্যালেন্স যোগ করেছেন!</b>\n<tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji> পরিমাণ: <b>${format_money_exact(add_amt)} USD</b>")
                    except Exception:
                        send_message(chat_id, "<tg-emoji emoji-id=\"5217822164362739968\">❌</tg-emoji> সঠিক পরিমাণ লিখুন (যেমন: <code>0.136</code>):")
                        return
                    delete_user_state(user_id)
                    return

                if is_admin and state_data == "ADMIN_SET_CHANNELS":
                    channels = [ch.strip() for ch in text.split(",") if ch.strip()]
                    set_force_channels(channels)
                    send_message(chat_id, f"<tg-emoji emoji-id=\"5841276284155467413\">✅</tg-emoji> <b>পুরোনো লিস্ট মুছে ফেলে নতুন ফোর্স জয়েন চ্যানেল/গ্রুপ সফলভাবে সেট করা হয়েছে!</b>", reply_markup=get_main_keyboard(is_admin))
                    delete_user_state(user_id)
                    return

                if is_admin and state_data == "ADMIN_UPLOAD_FILE":
                    lines = text.split("\n")
                    count = 0
                    for line in lines:
                        line_clean = line.strip()
                        if not line_clean:
                            continue
                        if "Phone Number" in line_clean or "Direct Link" in line_clean or "====" in line_clean or "VNUM" in line_clean or "Purchased" in line_clean or "Time:" in line_clean:
                            continue
                        
                        if "," in line_clean:
                            parts = [p.strip().strip('"').strip("'") for p in line_clean.split(",")]
                            if len(parts) >= 2:
                                phone = parts[0]
                                link = parts[1]
                                if phone and link and phone.startswith("+"):
                                    add_stock_item(phone, link)
                                    count += 1
                        elif "http" in line_clean:
                            for sep in ["----", "---", "--", " "]:
                                if sep in line_clean:
                                    parts = line_clean.split(sep, 1)
                                    phone = parts[0].strip()
                                    link = parts[1].strip()
                                    if phone and link and phone.startswith("+"):
                                        add_stock_item(phone, link)
                                        count += 1
                                    break

                    send_message(chat_id, f"<tg-emoji emoji-id=\"5841276284155467413\">✅</tg-emoji> সফলভাবে <b>{count}</b> টি নম্বর স্টক করা হয়েছে!", reply_markup=get_main_keyboard(is_admin))
                    delete_user_state(user_id)
                    return

                if is_admin and state_data == "ADMIN_UPLOAD_VPN_FILE":
                    lines = text.split("\n")
                    count = 0
                    for line in lines:
                        if "|" in line:
                            parts = line.split("|", 1)
                            srv = parts[0].strip().lower()
                            acc = parts[1].strip()
                            if srv in ["nord", "datama"] and acc:
                                add_vpn_stock_item(srv, acc)
                                count += 1
                    send_message(chat_id, f"<tg-emoji emoji-id=\"5841276284155467413\">✅</tg-emoji> সফলভাবে <b>{count}</b> টি VPN অ্যাকাউন্ট যোগ করা হয়েছে!", reply_markup=get_main_keyboard(is_admin))
                    delete_user_state(user_id)
                    return

                if isinstance(state_data, dict) and state_data.get("step") == "WAITING_AMOUNT":
                    try:
                        amount = float(text)
                        if amount < 0.5:
                            send_message(chat_id, "⚠️ <b>সর্বনিম্ন ডিপোজিট পরিমাণ 0.5 USDT হতে হবে!</b> দয়া করে সঠিক পরিমাণ লিখুন:")
                            return
                        set_user_state(user_id, {"step": "WAITING_TRX", "amount": amount})
                        send_message(chat_id, f"<tg-emoji emoji-id=\"5269657987219232606\">🟡</tg-emoji> <b>Binance Pay (USDT)</b>\n\n🆔 PayID: <code>{BINANCE_PAY_ID}</code>\n<tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji> পরিমাণ: {amount} USDT\n\nটাকা পাঠানোর পর আপনার <b>TrxID</b> বা অর্ডার আইডি লিখে পাঠান:", reply_markup=get_back_keyboard())
                        return
                    except ValueError:
                        send_message(chat_id, "<tg-emoji emoji-id=\"5217822164362739968\">❌</tg-emoji> সঠিক পরিমাণ লিখুন।")
                        return

                elif isinstance(state_data, dict) and state_data.get("step") == "WAITING_TRX":
                    set_user_state(user_id, {"step": "WAITING_SCREENSHOT", "amount": state_data["amount"], "trx_id": text})
                    send_message(chat_id, "📸 <b>ধন্যবাদ! এবার পেমেন্টের স্পষ্ট স্ক্রিনশট (Photo) পাঠান:</b>", reply_markup=get_back_keyboard())
                    return

                elif isinstance(state_data, dict) and state_data.get("step") == "WAITING_SCREENSHOT":
                    if "photo" in msg:
                        photo_id = msg["photo"][-1]["file_id"]
                        amt = state_data["amount"]
                        admin_markup = {
                            "inline_keyboard": [
                                [{"text": f"✅ Approve (${amt})", "callback_data": f"appusd_{user_id}_{amt}", "style": "success"}],
                                [{"text": "❌ Reject", "callback_data": f"dep_rej_{user_id}", "style": "danger"}]
                            ]
                        }
                        for aid in ADMIN_IDS:
                            if aid != 0:
                                send_photo_to_admin(aid, photo_id, f"📥 <b>নতুন ডিপোজিট রিকোয়েস্ট</b>\n👤 @{username} (<code>{user_id}</code>)\n<tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji> {amt} USDT\nTrxID: <code>{state_data['trx_id']}</code>", reply_markup=admin_markup)
                        send_message(chat_id, f"<tg-emoji emoji-id=\"5841276284155467413\">✅</tg-emoji> <b>আপনার ডিপোজিট তথ্য অ্যাডমিনের কাছে পাঠানো হয়েছে!</b> যাচাই করে ব্যালেন্স যোগ করা হবে।", reply_markup=get_main_keyboard(is_admin))
                        delete_user_state(user_id)
                        return
                    else:
                        send_message(chat_id, "<tg-emoji emoji-id=\"5217822164362739968\">❌</tg-emoji> অনুগ্রহ করে পেমেন্টের একটি স্ক্রিনশট ছবি পাঠান।", reply_markup=get_back_keyboard())
                        return

                if is_admin and state_data == "ADMIN_BROADCAST":
                    for u_id in get_all_users():
                        try: send_message(u_id, text)
                        except: pass
                    send_message(chat_id, f"<tg-emoji emoji-id=\"5841276284155467413\">✅</tg-emoji> <b>ব্রডকাস্ট সম্পন্ন হয়েছে!</b>", reply_markup=get_main_keyboard(is_admin))
                    delete_user_state(user_id)
                    return

            if text == "/start":
                send_message(chat_id, f"👋 <b>স্বাগতম {html.escape(first_name)}!</b>\n\nনিচের মেনু থেকে আপনার প্রয়োজনীয় সার্ভিসটি বেছে নিন:", reply_markup=get_main_keyboard(is_admin))

            elif text in ["🛒 𝗕𝗨𝗬 𝗡𝗨𝗠𝗕𝗘𝗥", "🛒 BUY NUMBER"]:
                markup = {
                    "inline_keyboard": [
                        [{"text": f"🇨🇦 𝗖𝗔𝗡𝗔𝗗𝗔 𝗪𝗦 (${format_money_exact(current_price)})", "callback_data": "confirm_buy_canada", "style": "success"}],
                        [{"text": "🔢 𝗠𝗨𝗟𝗧𝗜𝗣𝗟𝗘 𝗕𝗨𝗬", "callback_data": "buy_multi_num", "style": "primary"}]
                    ]
                }
                send_message(chat_id, f"<b><tg-emoji emoji-id=\"5397916757333654639\">🇨🇦</tg-emoji> <tg-emoji emoji-id=\"5429651785352501917\">💬</tg-emoji> Canada WhatsApp Service:</b>\n\nমূল্য: <b><tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji>" + format_money_exact(current_price) + " USD / Number</b>\n⚠️ <i>রিফান্ডযোগ্য নয় | নম্বর মেয়াদ ২০ দিন</i>", reply_markup=markup)

            elif text in ["🛡️ 𝗕𝗨𝗬 𝗩𝗣𝗡 / 𝗜𝗣", "🛡️ BUY VPN / IP"]:
                nord_pr = get_vpn_price('nord')
                datama_pr = get_vpn_price('datama')
                markup = {
                    "inline_keyboard": [
                        [{"text": f"🛡️ NordVPN (${nord_pr:.2f})", "callback_data": "buy_vpn_nord", "style": "primary"}],
                        [{"text": f"🌐 DatamaPlus IP (${datama_pr:.2f})", "callback_data": "buy_vpn_datama", "style": "primary"}]
                    ]
                }
                send_message(chat_id, f"<tg-emoji emoji-id=\"5420155432272438703\">🛡️</tg-emoji> <b>VPN & IP Service Options:</b>\n\nপছন্দের সার্ভিসটি সিলেক্ট করুন:", reply_markup=markup)

            elif text in ["💳 𝗗𝗘𝗣𝗢𝗦𝗜𝗧", "💳 DEPOSIT"]:
                markup = {"inline_keyboard": [[{"text": "🟡 Binance Pay (USDT)", "callback_data": "dep_binance", "style": "success"}]]}
                send_message(chat_id, f"<tg-emoji emoji-id=\"5377774889723798543\">💳</tg-emoji> <tg-emoji emoji-id=\"5269657987219232606\">🟡</tg-emoji> <b>Binance Deposit Gateway:</b>\n\nনিচের মাধ্যম থেকে ডিপোজিট করুন (মিনিমাম ০.৫ USDT):", reply_markup=markup)

            elif text in ["👤 𝗣𝗥𝗢𝗙𝗜𝗟𝗘", "👤 PROFILE"]:
                u = get_user(user_id)
                bal = format_money_exact(u[2]) if u else "0"
                tot = format_money_exact(u[3]) if u else "0"
                send_message(chat_id, f"👤 <b>Your Profile Information</b>\n\n🆔 আইডি: <code>{user_id}</code>\n<tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji> বর্তমান ব্যালেন্স: <b>${bal} USD</b>\n<tg-emoji emoji-id=\"5264713049637409446\">📊</tg-emoji> মোট রিচার্জ: <b>${tot} USD</b>", reply_markup=get_back_keyboard())

            elif text in ["🎧 𝗦𝗨𝗣𝗣𝗢𝗥𝗧", "🎧 SUPPORT"]:
                send_message(chat_id, f"🎧 <b>যেকোনো প্রয়োজনে যোগাযোগ করুন:</b>\n👉 @{SUPPORT_USERNAME}", reply_markup=get_back_keyboard())

            elif text in ["⚙️ 𝗔𝗗𝗠𝗜𝗡 𝗣𝗔𝗡𝗘𝗟", "⚙️ ADMIN PANEL"] and is_admin:
                msg_txt, markup = get_admin_panel_data()
                send_message(chat_id, msg_txt, reply_markup=markup)

        elif "callback_query" in update:
            cb = update["callback_query"]
            cb_id, chat_id, message_id, user_id, data = cb["id"], cb["message"]["chat"]["id"], cb["message"]["message_id"], cb["from"]["id"], cb.get("data", "")
            is_admin = is_user_admin(user_id)

            try: requests.post(BASE_URL + "answerCallbackQuery", json={"callback_query_id": cb_id}, timeout=5)
            except: pass

            current_price = get_number_price()

            if data == "noop": return

            if data == "cancel_multi_buy":
                delete_user_state(user_id)
                edit_message(chat_id, message_id, "❌ <b>মাল্টিপল বাই প্রসেস বাতিল করা হয়েছে।</b>", reply_markup=None)
                send_message(chat_id, "<b>🏠 মূল মেনুতে ফিরে আসা হয়েছে:</b>", reply_markup=get_main_keyboard(is_admin))
                return

            if data.startswith("buy_vpn_"):
                service = "nord" if "nord" in data else "datama"
                service_title = "NordVPN" if service == "nord" else "DatamaPlus IP"
                pr = get_vpn_price(service)
                u_info = get_user(user_id)
                bal = u_info[2] if u_info else 0.0

                if to_decimal(bal) < to_decimal(pr):
                    edit_message(chat_id, message_id, f"<tg-emoji emoji-id=\"5217822164362739968\">❌</tg-emoji> <b>অপর্যাপ্ত ব্যালেন্স!</b>\n{service_title} কিনতে <tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji>{pr:.2f} USD প্রয়োজন। আপনার ব্যালেন্স: <tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji>{format_money_exact(bal)} USD.")
                    return

                conf_markup = {
                    "inline_keyboard": [
                        [
                            {"text": "✅ Confirm Order", "callback_data": f"conf_vpn_{service}", "style": "success"},
                            {"text": "❌ Cancel", "callback_data": "cancel_vpn", "style": "danger"}
                        ]
                    ]
                }
                edit_message(chat_id, message_id, f"<tg-emoji emoji-id=\"5420155432272438703\">🛡️</tg-emoji> <b>{service_title} Order Confirmation</b>\n\n<tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji> মূল্য: <b>${pr:.2f} USD</b>\n<tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji> আপনার ব্যালেন্স: <b>${format_money_exact(bal)} USD</b>\n\nআপনি কি অর্ডারটি নিশ্চিত করতে চান?", reply_markup=conf_markup)
                return

            elif data.startswith("conf_vpn_"):
                service = "nord" if "nord" in data else "datama"
                service_title = "NordVPN" if service == "nord" else "DatamaPlus IP"
                pr = get_vpn_price(service)
                u_info = get_user(user_id)
                bal = u_info[2] if u_info else 0.0

                if to_decimal(bal) < to_decimal(pr):
                    edit_message(chat_id, message_id, f"<tg-emoji emoji-id=\"5217822164362739968\">❌</tg-emoji> <b>পর্যাপ্ত ব্যালেন্স নেই!</b>")
                    return

                deduct_balance(user_id, pr)
                order_id = save_vpn_order(user_id, service, pr)
                for aid in ADMIN_IDS:
                    if aid != 0:
                        send_message(aid, f"🚨 <b>NEW VPN / IP ORDER #{order_id}</b>\n\n👤 User ID: <code>{user_id}</code>\n🛡️ Service: {service_title}\n<tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji> Price: ${pr:.2f} USD\n\n👉 <i>এই মেসেজে Reply দিয়ে অ্যাকাউন্ট তথ্য পাঠান।</i>")
                edit_message(chat_id, message_id, f"<tg-emoji emoji-id=\"5841276284155467413\">✅</tg-emoji> <b>আপনার {service_title} অর্ডারটি সফলভাবে কনফার্ম হয়েছে!</b>\n\n ফি কাটা হয়েছে: <tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji>${pr:.2f} USD\n⏳ অল্প সময়ের মধ্যে অ্যাডমিন ডেলিভারি দিয়ে দেবেন।")
                return

            elif data == "cancel_vpn":
                edit_message(chat_id, message_id, f"<tg-emoji emoji-id=\"5217822164362739968\">❌</tg-emoji> <b>অর্ডারটি বাতিল করা হয়েছে।</b>")
                return

            elif data == "verify_join":
                if verify_force_join(user_id)[0]:
                    send_message(chat_id, f"<tg-emoji emoji-id=\"5841276284155467413\">✅</tg-emoji> <b>ভেরিফিকেশন সফল হয়েছে!</b>", reply_markup=get_main_keyboard(is_admin))
                else:
                    send_message(chat_id, "<tg-emoji emoji-id=\"5217822164362739968\">❌</tg-emoji> <b>দয়া করে সবকটি চ্যানেল বা গ্রুপে জয়েন করুন।</b>")

            elif data == "buy_multi_num":
                set_user_state(user_id, "BUY_MULTI_QTY")
                edit_message(chat_id, message_id, "🔢 <b>একসাথে কতগুলো নম্বর কিনতে চান সংখ্যা লিখে পাঠান:</b>\n(যেমন: 2, 5, 10)", reply_markup={"inline_keyboard": [[{"text": "❌ Cancel", "callback_data": "cancel_multi_buy"}], [{"text": "⬅️ Back", "callback_data": "back_to_buy_menu"}]]})

            elif data == "back_to_buy_menu":
                delete_user_state(user_id)
                markup = {
                    "inline_keyboard": [
                        [{"text": f"🇨🇦 𝗖𝗔𝗡𝗔𝗗𝗔 𝗪𝗦 (${format_money_exact(current_price)})", "callback_data": "confirm_buy_canada", "style": "success"}],
                        [{"text": "🔢 𝗠𝗨𝗟𝗧𝗜𝗣𝗟𝗘 𝗕𝗨𝗬", "callback_data": "buy_multi_num", "style": "primary"}]
                    ]
                }
                edit_message(chat_id, message_id, f"<b><tg-emoji emoji-id=\"5397916757333654639\">🇨🇦</tg-emoji> <tg-emoji emoji-id=\"5429651785352501917\">💬</tg-emoji> Canada WhatsApp Service:</b>\n\nমূল্য: <b><tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji>" + format_money_exact(current_price) + " USD / Number</b>\n⚠️ <i>রিফান্ডযোগ্য নয় | নম্বর মেয়াদ ২০ দিন</i>", reply_markup=markup)

            elif data == "confirm_buy_canada":
                u = get_user(user_id)
                bal = u[2] if u else 0.0
                if to_decimal(bal) < current_price:
                    edit_message(chat_id, message_id, f"<tg-emoji emoji-id=\"5217822164362739968\">❌</tg-emoji> <b>অপর্যাপ্ত ব্যালেন্স!</b> প্রয়োজন: <tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji>{format_money_exact(current_price)} USD")
                    return
                phone, link = pop_stock_item()
                if not phone:
                    edit_message(chat_id, message_id, "⚠️ <b>দুঃখিত! বর্তমানে স্টক খালি রয়েছে।</b>")
                    return
                
                order_id = save_active_order(user_id, phone, link)
                deduct_balance(user_id, current_price)
                record_sale_stat(1, current_price, get_cost_price())

                res_text = f"<tg-emoji emoji-id=\"5841276284155467413\">✅</tg-emoji> <b>নম্বর সফলভাবে বরাদ্দ করা হয়েছে!</b>\n\n<tg-emoji emoji-id=\"5397916757333654639\">🇨🇦</tg-emoji> <code>{phone}</code>\n{link}\n\nফি: <tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji>${format_money_exact(current_price)} USD"
                markup = {
                    "inline_keyboard": [
                        [{"text": "🔄 Check OTP", "callback_data": f"chk_otp_{phone}", "style": "primary"}],
                        [{"text": "🛒 Buy Another Number", "callback_data": "confirm_buy_canada", "style": "success"}]
                    ]
                }
                edit_message(chat_id, message_id, res_text, reply_markup=markup)

            elif data.startswith("chk_otp_"):
                phone = data.replace("chk_otp_", "")
                order = get_order_by_phone(phone)
                if order:
                    send_message(chat_id, f"⏳ <b>OTP এর জন্য অপেক্ষা করা হচ্ছে (১ মিনিট লাইভ চেকিং)...</b>\n📱 <code>{phone}</code>")
                    
                    def live_check_otp(target_chat_id, target_phone, target_link):
                        start_time = time.time()
                        while time.time() - start_time < 60:
                            try:
                                resp = requests.get(target_link, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                                clean = re.sub(r'<[^>]+>', ' ', resp.text)
                                m = re.search(r'\b(\d{3,4})[-]?(\d{3,4})\b', clean)
                                otp = "".join(m.groups()) if m else None
                                if otp:
                                    update_order_otp(target_phone, otp)
                                    app_type = "WB" if ("business" in resp.text.lower() or "smb" in resp.text.lower()) else "WA"
                                    send_message(target_chat_id, f"🎉 <tg-emoji emoji-id=\"5193063022226086560\">🔑</tg-emoji> <b>সফলভাবে OTP পাওয়া গেছে! ({app_type})</b>\n📱 নম্বর: <code>{target_phone}</code>\n🔑 <b>OTP Code:</b> <code>{otp}</code>")
                                    if OTP_GROUP_ID:
                                        masked_num = mask_phone_number(target_phone)
                                        send_message(OTP_GROUP_ID, f"🔥 <b>New OTP Received! ({app_type})</b>\n📱 <b>Number:</b> <code>{masked_num}</code>\n🔑 <b>OTP Code:</b> <code>{otp}</code>")
                                    return
                            except Exception:
                                pass
                            time.sleep(5)
                        
                        send_message(target_chat_id, f"⌛ <b>সময় শেষ!</b> নম্বর <code>{target_phone}</code> এর জন্য নির্ধারিত ১ মিনিটের মধ্যে কোনো OTP আসেনি। দয়া করে কিছুক্ষণ পর আবার চেক করুন।")

                    threading.Thread(target=live_check_otp, args=(chat_id, phone, order[2]), daemon=True).start()

            elif data == "admin_view_history" and is_admin:
                stats_cursor = daily_stats_col.find().sort("date", -1).limit(7)
                hist_text = "📊 <b>𝗟𝗔𝗦𝗧 𝟩 𝗗𝗔𝗬𝗦 𝗗𝗘𝗣𝗢𝗦𝗜𝗧 & 𝗣𝗥𝗢𝗙𝗜𝗧 𝗛𝗜𝗦𝗧𝗢𝗥𝗬</b>\n\n"
                for doc in stats_cursor:
                    hist_text += f"📅 <tg-emoji emoji-id=\"5264713049637409446\">📊</tg-emoji> <b>তারিখ:</b> {doc['date']}\n   ডিপোজিট: <tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji>${format_money_exact(doc.get('total_deposit', 0))} USDT\n   বিক্রয়: {doc.get('total_sold', 0)} টি\n   রেভিনিউ: <tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji>${format_money_exact(doc.get('total_revenue', 0))}\n   নেট প্রফিট: <tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji>${format_money_exact(doc.get('total_profit', 0))}\n\n"
                edit_message(chat_id, message_id, hist_text, reply_markup={"inline_keyboard": [[{"text": "⬅️ 𝗕𝗮𝗰𝗸", "callback_data": "admin_panel_back"}]]})

            elif data == "admin_panel_back" and is_admin:
                msg_txt, markup = get_admin_panel_data()
                edit_message(chat_id, message_id, msg_txt, reply_markup=markup)

            elif data.startswith("admin_daily_stats_") and is_admin:
                s_msg, s_markup = render_daily_stats_page(int(data.replace("admin_daily_stats_", "")))
                edit_message(chat_id, message_id, s_msg, reply_markup=s_markup)

            elif data == "admin_direct_add_balance" and is_admin:
                set_user_state(user_id, {"step": "ADMIN_ADD_BAL_USER"})
                send_message(chat_id, "➕ <b>ইউজার ব্যালেন্স যোগ করতে চান:</b>\n\nপ্রথমে যে ইউজারের ব্যালেন্স যোগ করবেন তার <b>User ID</b> লিখে পাঠান:", reply_markup=get_back_keyboard())

            elif data == "dep_binance":
                set_user_state(user_id, {"step": "WAITING_AMOUNT"})
                edit_message(chat_id, message_id, f"<tg-emoji emoji-id=\"5269657987219232606\">🟡</tg-emoji> <b>Binance Deposit Gateway:</b>\n\nকত USDT ডিপোজিট করতে চান সংখ্যাটি লিখে পাঠান (মিনিমাম ০.৫ USDT):", reply_markup={"inline_keyboard": [[{"text": "⬅️ Back", "callback_data": "back_to_main_menu"}]]})

            elif data == "back_to_main_menu":
                markup = {"inline_keyboard": [[{"text": "🟡 Binance Pay (USDT)", "callback_data": "dep_binance", "style": "success"}]]}
                edit_message(chat_id, message_id, f"<tg-emoji emoji-id=\"5377774889723798543\">💳</tg-emoji> <tg-emoji emoji-id=\"5269657987219232606\">🟡</tg-emoji> <b>Binance Deposit Gateway</b>\n\nপেমেন্ট মাধ্যম বেছে নিন:", reply_markup=markup)

            elif data == "admin_set_rate" and is_admin:
                set_user_state(user_id, "ADMIN_SET_PRICE")
                send_message(chat_id, "🏷️ নতুন মূল্য লিখে পাঠান:", reply_markup=get_back_keyboard())

            elif data == "admin_set_nord_price" and is_admin:
                set_user_state(user_id, "ADMIN_SET_PRICE_CUSTOM_nord")
                send_message(chat_id, "🛡️ NordVPN এর নতুন মূল্য লিখে পাঠান:", reply_markup=get_back_keyboard())

            elif data == "admin_set_datama_price" and is_admin:
                set_user_state(user_id, "ADMIN_SET_PRICE_CUSTOM_datama")
                send_message(chat_id, "🌐 DatamaPlus এর নতুন মূল্য লিখে পাঠান:", reply_markup=get_back_keyboard())

            elif data == "admin_set_channels" and is_admin:
                set_user_state(user_id, "ADMIN_SET_CHANNELS")
                send_message(chat_id, "📢 চ্যানেল ইউজারনেম বা গ্রুপ Chat ID দিন (একাধিক হলে কমা দিয়ে লিখুন যেমন: @channel1, -100123456789):\n⚠️ <i>মনে রাখবেন, নতুন লিস্ট সেট করলে আগেরগুলো মুছে যাবে।</i>", reply_markup=get_back_keyboard())

            elif data == "admin_upload_vpn_file" and is_admin:
                set_user_state(user_id, "ADMIN_UPLOAD_VPN_FILE")
                send_message(chat_id, "📁 VPN স্টক টেক্সট আকারে পাঠান (Format: <code>nord | account_info</code> বা <code>datama | account_info</code>)", reply_markup=get_back_keyboard())

            elif data == "admin_toggle_bot_off" and is_admin:
                set_bot_status("OFF")
                msg_txt, markup = get_admin_panel_data()
                edit_message(chat_id, message_id, msg_txt, reply_markup=markup)

            elif data == "admin_toggle_bot_on" and is_admin:
                set_bot_status("ON")
                msg_txt, markup = get_admin_panel_data()
                edit_message(chat_id, message_id, msg_txt, reply_markup=markup)

            elif data == "admin_broadcast" and is_admin:
                set_user_state(user_id, "ADMIN_BROADCAST")
                send_message(chat_id, "📢 ব্রডকাস্ট মেসেজটি লিখে পাঠান:", reply_markup=get_back_keyboard())

            elif data == "admin_upload_file" and is_admin:
                set_user_state(user_id, "ADMIN_UPLOAD_FILE")
                send_message(chat_id, "📁 নম্বর স্টক টেক্সট ফাইল (.txt) আকারে আপলোড করুন বা টেক্সট পেস্ট করুন:", reply_markup=get_back_keyboard())

            elif data == "admin_view_stock" and is_admin:
                items = get_all_stock()
                send_message(chat_id, f"📊 <b>Stock Status:</b>\nCanada Numbers: {len(items)} Pcs\nNordVPN: {get_vpn_stock_count('nord')} Pcs\nDatamaPlus: {get_vpn_stock_count('datama')} Pcs")

            elif data == "admin_delete_stock_confirm" and is_admin:
                edit_message(chat_id, message_id, "⚠️ <b>সব স্টক মুছে ফেলতে চান?</b>", reply_markup={"inline_keyboard": [[{"text": "✅ Yes, Delete", "callback_data": "admin_delete_stock_execute", "style": "danger"}]]})

            elif data == "admin_delete_stock_execute" and is_admin:
                clear_all_stock()
                edit_message(chat_id, message_id, "🗑️ <b>স্টক সফলভাবে খালি করা হয়েছে!</b>")

            elif data.startswith("appusd_") and is_admin:
                parts = data.split("_")
                u_id = int(parts[1])
                amt = float(parts[2])
                update_balance(u_id, amt)
                record_deposit_stat(amt)
                
                old_caption = cb["message"].get("caption", cb["message"].get("text", ""))
                new_caption = old_caption + f"\n\n<b>✅ Approved by Admin ({user_id})</b>"
                edit_caption(chat_id, message_id, new_caption, reply_markup=None)
                
                send_message(chat_id, f"<tg-emoji emoji-id=\"5841276284155467413\">✅</tg-emoji> <b>Balance credited & recorded!</b>")
                send_message(u_id, f"🎉 <b>আপনার ডিপোজিট সফল হয়েছে! <tg-emoji emoji-id=\"5312361253610475399\">💲</tg-emoji>${format_money_exact(amt)} USD অ্যাকাউন্টে যোগ করা হয়েছে।</b>")

            elif data.startswith("dep_rej_") and is_admin:
                u_id = int(data.replace("dep_rej_", ""))
                
                old_caption = cb["message"].get("caption", cb["message"].get("text", ""))
                new_caption = old_caption + f"\n\n<b>❌ Rejected by Admin ({user_id})</b>"
                edit_caption(chat_id, message_id, new_caption, reply_markup=None)
                
                send_message(u_id, f"<tg-emoji emoji-id=\"5217822164362739968\">❌</tg-emoji> <b>আপনার ডিপোজিট প্রুফ রিজেক্ট করা হয়েছে!</b>")
                send_message(chat_id, "<tg-emoji emoji-id=\"5217822164362739968\">❌</tg-emoji> <b>Deposit rejected.</b>")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    print("🚀 Canada OTP Bot Engine Online with Fixed Deposit & Approvals...")
    offset = 0
    while True:
        try:
            res = requests.get(BASE_URL + "getUpdates", params={"offset": offset, "timeout": 20}, timeout=25).json()
            if res.get("ok"):
                for update in res.get("result", []):
                    offset = update["update_id"] + 1
                    threading.Thread(target=lambda u: handle_update(u), args=(update,), daemon=True).start()
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(3)
