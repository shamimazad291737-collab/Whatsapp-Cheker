const { default: makeWASocket, useMultiFileAuthState, disconnectReason, Browsers } = require('@whiskeysockets/baileys');
const TelegramBot = require('node-telegram-bot-api');
const express = require('express');

// ১. কনফিগারেশন
const TELEGRAM_TOKEN = '8828385782:AAHbRFf0YcFqmWSXiAH1mYXMpUxRdACRFhE'; // BotFather-এর টোকেন
const ADMIN_ID = 7388500439; // আপনার Numeric Telegram ID (@userinfobot থেকে নেওয়া)
let currentPassword = "291736"; // বটের পাসওয়ার্ড

const app = express();
const PORT = process.env.PORT || 3000;
app.get('/', (req, res) => res.send('Bot is Live!'));
app.listen(PORT, () => console.log(`Server running on port ${PORT}`));

const bot = new TelegramBot(TELEGRAM_TOKEN, { polling: true });
const userSockets = {};
const userStates = {};
const authenticatedUsers = new Set(); // পাসওয়ার্ড দেওয়া ইউজারদের লিস্ট

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// মূল বাটন মেনু
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
            bot.sendMessage(chatId, "✅ **WhatsApp successfully connected!**\n\nএখন '📱 Check Number' বাটনে ক্লিক করে নম্বর ফিল্টার করুন।", {
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

// /start কমান্ড
bot.onText(/\/start/, (msg) => {
    const chatId = msg.chat.id;

    // অ্যাডমিনকে সরাসরি ঢুকতে দেওয়া হবে
    if (msg.from.id === ADMIN_ID) {
        authenticatedUsers.add(chatId);
        return bot.sendMessage(chatId, "👑 **স্বাগতম অ্যাডমিন!**\n\nপাসওয়ার্ড পরিবর্তন করতে লিখুন: `/setpass নতুন_পাসওয়ার্ড`", {
            parse_mode: "Markdown",
            reply_markup: getMainButtons()
        });
    }

    // ইউজার যদি অলরেডি পাসওয়ার্ড দিয়ে থাকে
    if (authenticatedUsers.has(chatId)) {
        bot.sendMessage(chatId, "👋 **স্বাগতম!** নিচের বাটন থেকে অপশন বেছে নিন:", {
            parse_mode: "Markdown",
            reply_markup: getMainButtons()
        });
    } else {
        userStates[chatId] = "WAITING_FOR_PASSWORD";
        bot.sendMessage(chatId, "🔒 **বটটি ব্যবহার করতে পাসওয়ার্ড লাগবে।**\n\nঅনুগোছ করে পাসওয়ার্ডটি পাঠান:");
    }
});

// অ্যাডমিনের পাসওয়ার্ড পরিবর্তনের কমান্ড
bot.onText(/\/setpass (.+)/, (msg, match) => {
    const chatId = msg.chat.id;

    if (msg.from.id !== ADMIN_ID) {
        return bot.sendMessage(chatId, "⚠️ শুধুমাত্র অ্যাডমিন পাসওয়ার্ড পরিবর্তন করতে পারবে।");
    }

    const newPass = match[1].trim();
    currentPassword = newPass;
    bot.sendMessage(chatId, `✅ নতুন পাসওয়ার্ড সেট করা হয়েছে: \`${newPass}\``, { parse_mode: "Markdown" });
});

// বাটন ইন্টারঅ্যাকশন
bot.on('callback_query', async (query) => {
    const chatId = query.message.chat.id;
    const action = query.data;

    bot.answerCallbackQuery(query.id);

    // পাসওয়ার্ড ভেরিফিকেশন চেক
    if (!authenticatedUsers.has(chatId) && query.from.id !== ADMIN_ID) {
        userStates[chatId] = "WAITING_FOR_PASSWORD";
        return bot.sendMessage(chatId, "🔒 **দয়া করে প্রথমে সঠিক পাসওয়ার্ড দিয়ে লগইন করুন।**");
    }

    if (action === "cmd_link") {
        userStates[chatId] = "WAITING_FOR_LINK_NUMBER";
        bot.sendMessage(chatId, "📲 **আপনার WhatsApp নম্বরটি দিন** (যেমন: `8801700000000`):", { parse_mode: "Markdown" });

    } else if (action === "cmd_check") {
        const waSock = userSockets[chatId];
        if (!waSock || !waSock.authState.creds.registered) {
            return bot.sendMessage(chatId, "⚠️ **আপনার WhatsApp কানেক্ট করা নেই!**\n\nপ্রথমে '🔗 Link WhatsApp' বাটনে চাপ দিন।", {
                reply_markup: getMainButtons()
            });
        }
        userStates[chatId] = "WAITING_FOR_CHECK_NUMBER";
        bot.sendMessage(chatId, "🔍 **যে নম্বরটি চেক করতে চান সেটি পাঠান** (যেমন: `8801800000000`):", { parse_mode: "Markdown" });

    } else if (action === "cmd_help") {
        const isConnected = userSockets[chatId]?.authState?.creds?.registered ? "✅ Connected" : "❌ Not Connected";
        bot.sendMessage(chatId, `ℹ️ **Bot Status:**\n- WhatsApp Status: ${isConnected}`, {
            reply_markup: getMainButtons()
        });
    }
});

// মেসেজ রিসিভার
bot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    const text = msg.text?.trim();

    if (!text || text.startsWith('/')) return;

    const state = userStates[chatId];

    // ১. পাসওয়ার্ড ইনপুট ভেরিফিকেশন
    if (!authenticatedUsers.has(chatId) && msg.from.id !== ADMIN_ID) {
        if (text === currentPassword) {
            authenticatedUsers.add(chatId);
            delete userStates[chatId];
            return bot.sendMessage(chatId, "🎉 **পাসওয়ার্ড সঠিক হয়েছে!**\n\nনিচের বাটন থেকে অপশন বেছে নিন:", {
                parse_mode: "Markdown",
                reply_markup: getMainButtons()
            });
        } else {
            return bot.sendMessage(chatId, "❌ **ভুল পাসওয়ার্ড!** আবার চেষ্টা করুন:");
        }
    }

    // ২. হোয়াটসঅ্যাপ লিঙ্ক করার নম্বর ইনপুট
    if (state === "WAITING_FOR_LINK_NUMBER") {
        delete userStates[chatId];
        const phone = text.replace('+', '').replace(/ /g, '');

        if (isNaN(phone)) {
            return bot.sendMessage(chatId, "❌ সঠিক নম্বর দিন। উদাহরণ: `8801700000000`", { reply_markup: getMainButtons() });
        }

        bot.sendMessage(chatId, "⏳ Pairing Code তৈরি করা হচ্ছে...");

        try {
            const waSock = await getUserSocket(chatId);
            await delay(5000);

            let code = await waSock.requestPairingCode(phone);
            code = code?.match(/.{1,4}/g)?.join("-") || code;

            bot.sendMessage(chatId, `🔑 **আপনার Pairing Code:** \`${code}\`\n\nWhatsApp > Linked Devices > Link with phone number-এ কোডটি বসান।`, {
                parse_mode: "Markdown",
                reply_markup: getMainButtons()
            });
        } catch (err) {
            bot.sendMessage(chatId, "❌ কোড জেনারেট হতে সমস্যা হয়েছে।", { reply_markup: getMainButtons() });
        }

    // ৩. নম্বর চেক ইনপুট
    } else if (state === "WAITING_FOR_CHECK_NUMBER" || userSockets[chatId]?.authState?.creds?.registered) {
        delete userStates[chatId];
        const waSock = userSockets[chatId];

        if (!waSock || !waSock.authState.creds.registered) {
            return bot.sendMessage(chatId, "⚠️ আপনার WhatsApp কানেক্ট করা নেই!", { reply_markup: getMainButtons() });
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
                bot.sendMessage(chatId, `📱 নম্বর: +${checkPhone}\n✅ **FRESH / HIGH OTP RATE** (ওটিপি আসবে)`, { reply_markup: getMainButtons() });
            }
        } catch (error) {
            bot.sendMessage(chatId, "❌ চেক করতে সমস্যা হয়েছে।", { reply_markup: getMainButtons() });
        }
    }
});
