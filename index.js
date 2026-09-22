const { default: makeWASocket, useMultiFileAuthState, disconnectReason, Browsers } = require('@whiskeysockets/baileys');
const TelegramBot = require('node-telegram-bot-api');
const express = require('express');

const TELEGRAM_TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN';

const app = express();
const PORT = process.env.PORT || 3000;
app.get('/', (req, res) => res.send('Bot is Live!'));
app.listen(PORT, () => console.log(`Server running on port ${PORT}`));

const bot = new TelegramBot(TELEGRAM_TOKEN, { polling: true });
const userSockets = {};
const userStates = {}; // ইউজার ইনপুট ট্র্যাক করার জন্য

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function getUserSocket(chatId) {
    if (userSockets[chatId]) return userSockets[chatId];

    const sessionDir = `./sessions/session_${chatId}`;
    const { state, saveCreds } = await useMultiFileAuthState(sessionDir);

    const waSock = makeWASocket({
        auth: state,
        printQRInTerminal: false,
        browser: Browsers.macOS('Desktop'),
        syncFullHistory: false
    });

    waSock.ev.on('creds.update', saveCreds);
    waSock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect } = update;
        if (connection === 'open') {
            bot.sendMessage(chatId, "✅ **WhatsApp successfully connected!**\n\nএখন নিচের '📱 Check Number' বাটনে ক্লিক করে যেকোনো নম্বর ফিল্টার করতে পারবেন।", {
                parse_mode: "Markdown",
                reply_markup: getMainButtons()
            });
        } else if (connection === 'close') {
            delete userSockets[chatId];
            const shouldReconnect = (lastDisconnect.error?.output?.statusCode !== disconnectReason.loggedOut);
            if (shouldReconnect) getUserSocket(chatId);
        }
    });

    userSockets[chatId] = waSock;
    return waSock;
}

// মূল বাটন ইন্টারফেস
function getMainButtons() {
    return {
        inline_keyboard: [
            [
                { text: "🔗 Link WhatsApp", callback_data: "cmd_link" },
                { text: "📱 Check Number", callback_data: "cmd_check" }
            ],
            [
                { text: "ℹ️ Help & Status", callback_data: "cmd_help" }
            ]
        ]
    };
}

// /start কমান্ড
bot.onText(/\/start/, (msg) => {
    bot.sendMessage(msg.chat.id, "👋 **স্বাগতম WhatsApp Checker বট-এ!**\n\nনিচের বাটন থেকে আপনার পছন্দমতো অপশন বেছে নিন:", {
        parse_mode: "Markdown",
        reply_markup: getMainButtons()
    });
});

// বাটন ক্লিকে রেসপন্স (Callback Query)
bot.on('callback_query', async (query) => {
    const chatId = query.message.chat.id;
    const action = query.data;

    // বাটন ক্লিক রিসিভ একনলেজমেন্ট
    bot.answerCallbackQuery(query.id);

    if (action === "cmd_link") {
        userStates[chatId] = "WAITING_FOR_LINK_NUMBER";
        bot.sendMessage(chatId, "📲 **আপনার WhatsApp নম্বরটি দিন** (যেমন: `8801700000000`):\n\n⚠️ রেস্ট্রিকশন এড়াতে অবশ্যই কান্ট্রি কোডসহ দিন।", { parse_mode: "Markdown" });

    } else if (action === "cmd_check") {
        const waSock = userSockets[chatId];
        if (!waSock || !waSock.authState.creds.registered) {
            return bot.sendMessage(chatId, "⚠️ **আপনার WhatsApp কানেক্ট করা নেই!**\n\nপ্রথমে '🔗 Link WhatsApp' বাটনে চাপ দিয়ে অ্যাকাউন্ট যুক্ত করুন।", {
                reply_markup: getMainButtons()
            });
        }
        userStates[chatId] = "WAITING_FOR_CHECK_NUMBER";
        bot.sendMessage(chatId, "🔍 **যে নম্বরটি চেক করতে চান সেটি পাঠান** (যেমন: `8801800000000`):", { parse_mode: "Markdown" });

    } else if (action === "cmd_help") {
        const isConnected = userSockets[chatId]?.authState?.creds?.registered ? "✅ Connected" : "❌ Not Connected";
        bot.sendMessage(chatId, `ℹ️ **Bot Status:**\n- WhatsApp Status: ${isConnected}\n\nধাপসমূহ:\n১. 'Link WhatsApp' বাটনে চাপুন ও নম্বর দিন।\n২. পাওয়া ৮ ডিজিটের কোডটি WhatsApp Linked Devices-এ বসান।\n৩. অ্যাকাউন্ট কানেক্ট হলে 'Check Number' দিয়ে ওটিপি ফিল্টার করুন।`, {
            reply_markup: getMainButtons()
        });
    }
});

// মেসেজ রিসিভার (ইনপুট প্রসেস করা)
bot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    const text = msg.text?.trim();

    if (!text || text.startsWith('/')) return;

    const state = userStates[chatId];

    // ১. হোয়াটসঅ্যাপ লিঙ্ক করার নম্বর ইনপুট
    if (state === "WAITING_FOR_LINK_NUMBER") {
        delete userStates[chatId];
        const phone = text.replace('+', '').replace(/ /g, '');

        if (isNaN(phone)) {
            return bot.sendMessage(chatId, "❌ সঠিক নম্বর দিন। উদাহরণ: `8801700000000`", { reply_markup: getMainButtons() });
        }

        bot.sendMessage(chatId, "⏳ Pairing Code তৈরি করা হচ্ছে, অনুগ্রহ করে কয়েক সেকেন্ড অপেক্ষা করুন...");

        try {
            const waSock = await getUserSocket(chatId);
            await delay(5000); // Anti-spam delay

            let code = await waSock.requestPairingCode(phone);
            code = code?.match(/.{1,4}/g)?.join("-") || code;

            bot.sendMessage(chatId, `🔑 **আপনার Pairing Code:** \`${code}\`\n\n১. আপনার মোবাইলের WhatsApp খুলুন > Settings > Linked Devices\n২. **Link with phone number** সিলেক্ট করুন\n৩. উপরের কোডটি বসিয়ে দিন।`, {
                parse_mode: "Markdown",
                reply_markup: getMainButtons()
            });
        } catch (err) {
            bot.sendMessage(chatId, "❌ কোড জেনারেট হতে সমস্যা হয়েছে। হোয়াটসঅ্যাপ রেস্ট্রিকশনে থাকলে বা বারবার চেষ্টার কারণে এটি হতে পারে।", { reply_markup: getMainButtons() });
        }

    // ২. নম্বর চেক করার ইনপুট
    } else if (state === "WAITING_FOR_CHECK_NUMBER" || userSockets[chatId]?.authState?.creds?.registered) {
        delete userStates[chatId];
        const waSock = userSockets[chatId];

        if (!waSock || !waSock.authState.creds.registered) {
            return bot.sendMessage(chatId, "⚠️ আপনার WhatsApp কানেক্ট করা নেই! আগে লিঙ্ক করুন।", { reply_markup: getMainButtons() });
        }

        const checkPhone = text.replace('+', '').replace(/ /g, '').replace(/-/g, '');
        if (isNaN(checkPhone)) return bot.sendMessage(chatId, "❌ সঠিক নম্বর দিন।", { reply_markup: getMainButtons() });

        bot.sendMessage(chatId, `⏳ \`+${checkPhone}\` নম্বরটি চেক করা হচ্ছে...`, { parse_mode: "Markdown" });

        try {
            await delay(2000);
            const [result] = await waSock.onWhatsApp(checkPhone);

            if (result && result.exists) {
                bot.sendMessage(chatId, `📱 নম্বর: +${checkPhone}\n❌ **LOGIN NOT AVAILABLE** (অ্যাকাউন্ট তৈরি করা আছে)`, { reply_markup: getMainButtons() });
            } else {
                bot.sendMessage(chatId, `📱 নম্বর: +${checkPhone}\n✅ **FRESH / HIGH OTP RATE** (হোয়াটসঅ্যাপ অ্যাকাউন্ট নেই, ওটিপি আসবে)`, { reply_markup: getMainButtons() });
            }
        } catch (error) {
            bot.sendMessage(chatId, "❌ চেক করতে সমস্যা হয়েছে। আবার চেষ্টা করুন।", { reply_markup: getMainButtons() });
        }
    }
});
                
