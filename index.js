const { default: makeWASocket, useMultiFileAuthState, disconnectReason } = require('@whiskeysockets/baileys');
const TelegramBot = require('node-telegram-bot-api');

// ১. কনফিগারেশন
const TELEGRAM_TOKEN = '8828385782:AAHbRFf0YcFqmWSXiAH1mYXMpUxRdACRFhE'; // BotFather এর টোকেন
const ADMIN_ID = 7388500439; // আপনার Numeric ID (@userinfobot থেকে নেওয়া)
const MY_PHONE_NUMBER = '8801XXXXXXXXX'; // আপনার আসল WhatsApp নম্বর (কোড নেওয়ার জন্য)

let currentPassword = "1234";
const authenticatedUsers = new Set();

const bot = new TelegramBot(TELEGRAM_TOKEN, { polling: true });
let waSock = null;

// ২. WhatsApp কানেকশন + Pairing Code মেথড
async function connectToWhatsApp() {
    const { state, saveCreds } = await useMultiFileAuthState('auth_info_baileys');
    
    waSock = makeWASocket({
        auth: state,
        printQRInTerminal: false // QR code বন্ধ রাখা হলো
    });

    // মোবাইল নম্বর দিয়ে Pairing Code জেনারেট করা
    if (!waSock.authState.creds.registered) {
        setTimeout(async () => {
            try {
                let code = await waSock.requestPairingCode(MY_PHONE_NUMBER);
                code = code?.match(/.{1,4}/g)?.join("-") || code;
                console.log(`\n=========================================\nYOUR WHATSAPP PAIRING CODE: ${code}\n=========================================\n`);
            } catch (err) {
                console.error("Pairing Code Error: ", err);
            }
        }, 3000);
    }

    waSock.ev.on('creds.update', saveCreds);

    waSock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect } = update;
        if (connection === 'close') {
            const shouldReconnect = (lastDisconnect.error?.output?.statusCode !== disconnectReason.loggedOut);
            if (shouldReconnect) connectToWhatsApp();
        } else if (connection === 'open') {
            console.log('WhatsApp Connected Successfully via Pairing Code!');
        }
    });
}

connectToWhatsApp();

// ৩. টেলিগ্রাম স্টার্ট কমান্ড (/start)
bot.onText(/\/start/, (msg) => {
    const chatId = msg.chat.id;

    if (msg.from.id === ADMIN_ID) {
        authenticatedUsers.add(chatId);
        return bot.sendMessage(chatId, "👑 স্বাগতম অ্যাডমিন! বট ব্যবহারের জন্য প্রস্তুত।\n\nপাসওয়ার্ড বদলাতে লিখুন: `/setpass নতুন_পাসওয়ার্ড`", { parse_mode: "Markdown" });
    }

    if (authenticatedUsers.has(chatId)) {
        bot.sendMessage(chatId, "✅ আপনি অলরেডি লগইন আছেন। চেক করতে যেকোনো নম্বর পাঠান।");
    } else {
        bot.sendMessage(chatId, "🔒 বটটি ব্যবহার করতে পাসওয়ার্ড লাগবে।\n\nলিখুন: `/pass পাসওয়ার্ড`", { parse_mode: "Markdown" });
    }
});

// ৪. পাসওয়ার্ড দিয়ে লগইন (/pass password)
bot.onText(/\/pass (.+)/, (msg, match) => {
    const chatId = msg.chat.id;
    const inputPass = match[1].trim();

    if (inputPass === currentPassword) {
        authenticatedUsers.add(chatId);
        bot.sendMessage(chatId, "🎉 সঠিক পাসওয়ার্ড! এবার নম্বর পাঠান (যেমন: 8801700000000)।");
    } else {
        bot.sendMessage(chatId, "❌ ভুল পাসওয়ার্ড! আবার চেষ্টা করুন।");
    }
});

// ৫. পাসওয়ার্ড পরিবর্তন (/setpass new_password)
bot.onText(/\/setpass (.+)/, (msg, match) => {
    const chatId = msg.chat.id;

    if (msg.from.id !== ADMIN_ID) {
        return bot.sendMessage(chatId, "⚠️ শুধু অ্যাডমিন পাসওয়ার্ড পরিবর্তন করতে পারবে।");
    }

    const newPass = match[1].trim();
    currentPassword = newPass;
    bot.sendMessage(chatId, `✅ নতুন পাসওয়ার্ড: \`${newPass}\``, { parse_mode: "Markdown" });
});

// ৬. নম্বর চেকিং মেসেজ
bot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    const text = msg.text?.trim();

    if (!text || text.startsWith('/')) return;

    if (!authenticatedUsers.has(chatId) && msg.from.id !== ADMIN_ID) {
        return bot.sendMessage(chatId, "🔒 পাসওয়ার্ড দিয়ে লগইন করুন।\nলিখুন: `/pass পাসওয়ার্ড`", { parse_mode: "Markdown" });
    }

    const phone = text.replace('+', '').replace(/ /g, '').replace(/-/g, '');

    if (isNaN(phone)) {
        return bot.sendMessage(chatId, "❌ অনুগ্রহ করে সঠিক নম্বর দিন।");
    }

    if (!waSock) {
        return bot.sendMessage(chatId, "⚠️ WhatsApp কানেকশন রেডি হচ্ছে, একটু পর চেষ্টা করুন।");
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
