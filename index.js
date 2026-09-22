const { default: makeWASocket, useMultiFileAuthState, disconnectReason } = require('@whiskeysockets/baileys');
const TelegramBot = require('node-telegram-bot-api');

// ১. কনফিগারেশন
const TELEGRAM_TOKEN = '8828385782:AAHbRFf0YcFqmWSXiAH1mYXMpUxRdACRFhE'; // BotFather থেকে নেওয়া টোকেন
const ADMIN_ID = 7388500439; // আপনার টেলিগ্রাম নিউমেরিক ID (না জানলে @userinfobot থেকে দেখে নিন)

let currentPassword = "1234"; // ডিফল্ট পাসওয়ার্ড (পরে চেঞ্জ করতে পারবেন)
const authenticatedUsers = new Set(); // যে ব্যবহারকারীরা সঠিক পাসওয়ার্ড দিয়েছে

const bot = new TelegramBot(TELEGRAM_TOKEN, { polling: true });
let waSock = null;

// ২. WhatsApp কানেকশন
async function connectToWhatsApp() {
    const { state, saveCreds } = await useMultiFileAuthState('auth_info_baileys');
    
    waSock = makeWASocket({
        auth: state,
        printQRInTerminal: true
    });

    waSock.ev.on('creds.update', saveCreds);

    waSock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect } = update;
        if (connection === 'close') {
            const shouldReconnect = (lastDisconnect.error?.output?.statusCode !== disconnectReason.loggedOut);
            console.log('Connection closed. Reconnecting...', shouldReconnect);
            if (shouldReconnect) connectToWhatsApp();
        } else if (connection === 'open') {
            console.log('WhatsApp Connected Successfully!');
        }
    });
}

connectToWhatsApp();

// ৩. টেলিগ্রাম স্টার্ট কমান্ড (/start)
bot.onText(/\/start/, (msg) => {
    const chatId = msg.chat.id;

    // অ্যাডমিন হলে অটোমেটিক এক্সেস পাবে
    if (msg.from.id === ADMIN_ID) {
        authenticatedUsers.add(chatId);
        return bot.sendMessage(chatId, "👑 স্বাগতম অ্যাডমিন! আপনি সরাসরি বট ব্যবহার করতে পারবেন।\n\nপাসওয়ার্ড পরিবর্তন করতে লিখুন:\n`/setpass নতুন_পাসওয়ার্ড`", { parse_mode: "Markdown" });
    }

    if (authenticatedUsers.has(chatId)) {
        bot.sendMessage(chatId, "✅ আপনি অলরেডি লগইন অবস্থায় আছেন। এবার চেক করার জন্য হোয়াটসঅ্যাপ নম্বর পাঠান।");
    } else {
        bot.sendMessage(chatId, "🔒 এই বটটি ব্যবহার করতে পাসওয়ার্ড প্রয়োজন।\n\nঅনুগ্রহ করে পাসওয়ার্ডটি এভাবে পাঠান:\n`/pass আপনার_পাসওয়ার্ড`", { parse_mode: "Markdown" });
    }
});

// ৪. পাসওয়ার্ড দিয়ে লগইন করা (/pass password)
bot.onText(/\/pass (.+)/, (msg, match) => {
    const chatId = msg.chat.id;
    const inputPass = match[1].trim();

    if (inputPass === currentPassword) {
        authenticatedUsers.add(chatId);
        bot.sendMessage(chatId, "🎉 সঠিক পাসওয়ার্ড! আপনার এক্সেস আনলক হয়েছে।\n\nএখন যেকোনো দেশের নম্বর পাঠান (যেমন: 8801700000000), আমি চেক করে দেব।");
    } else {
        bot.sendMessage(chatId, "❌ ভুল পাসওয়ার্ড! সঠিক পাসওয়ার্ড দিয়ে আবার চেষ্টা করুন।");
    }
});

// ৫. অ্যাডমিন কর্তৃক পাসওয়ার্ড পরিবর্তন (/setpass new_password)
bot.onText(/\/setpass (.+)/, (msg, match) => {
    const chatId = msg.chat.id;

    // শুধু অ্যাডমিন পাসওয়ার্ড পরিবর্তন করতে পারবে
    if (msg.from.id !== ADMIN_ID) {
        return bot.sendMessage(chatId, "⚠️ আপনি এই বটের অ্যাডমিন নন, তাই পাসওয়ার্ড পরিবর্তন করতে পারবেন না।");
    }

    const newPass = match[1].trim();
    currentPassword = newPass;
    bot.sendMessage(chatId, `✅ সফলতা! নতুন পাসওয়ার্ড সেট করা হয়েছে: \`${newPass}\``, { parse_mode: "Markdown" });
});

// ৬. নম্বর চেকিং মেসেজ হ্যান্ডলার
bot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    const text = msg.text?.trim();

    if (!text || text.startsWith('/')) return;

    // পাসওয়ার্ড চেক
    if (!authenticatedUsers.has(chatId) && msg.from.id !== ADMIN_ID) {
        return bot.sendMessage(chatId, "🔒 এটি একটি প্রাইভেট বট। ব্যবহার করার আগে পাসওয়ার্ড দিয়ে লগইন করুন।\nলিখুন: `/pass পাসওয়ার্ড`", { parse_mode: "Markdown" });
    }

    const phone = text.replace('+', '').replace(/ /g, '').replace(/-/g, '');

    if (isNaN(phone)) {
        return bot.sendMessage(chatId, "❌ অনুগ্রহ করে সঠিক নম্বর দিন।");
    }

    if (!waSock) {
        return bot.sendMessage(chatId, "⚠️ WhatsApp কানেকশন রেডি হচ্ছে, কয়েক সেকেন্ড পর আবার চেষ্টা করুন।");
    }

    bot.sendMessage(chatId, `⏳ ${phone} নম্বরটি চেক করা হচ্ছে...`);

    try {
        const [result] = await waSock.onWhatsApp(phone);

        if (result && result.exists) {
            bot.sendMessage(chatId, `📱 নম্বর: +${phone}\n❌ **LOGIN NOT AVAILABLE** (নম্বরটি অলরেডি সক্রিয় আছে)`);
        } else {
            bot.sendMessage(chatId, `📱 নম্বর: +${phone}\n✅ **FRESH / HIGH OTP RATE** (হোয়াটসঅ্যাপে অ্যাকাউন্ট নেই, ওটিপি আসবে)`);
        }
    } catch (error) {
        console.error(error);
        bot.sendMessage(chatId, "❌ নম্বর চেক করতে সমস্যা হয়েছে। আবার চেষ্টা করুন।");
    }
});
