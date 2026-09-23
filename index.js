const { default: makeWASocket, useMultiFileAuthState, disconnectReason, fetchLatestBaileysVersion, Browsers } = require('@whiskeysockets/baileys');
const TelegramBot = require('node-telegram-bot-api');
const express = require('express');
const fs = require('fs');

const TELEGRAM_TOKEN = process.env.TELEGRAM_TOKEN; 
const ADMIN_ID = 7388500439; 
let currentPassword = "291736"; 

if (!TELEGRAM_TOKEN) {
    console.error("ERROR: TELEGRAM_TOKEN missing in Environment Variables!");
    process.exit(1);
}

const app = express();
const PORT = process.env.PORT || 3000;
app.get('/', (req, res) => res.send('Bot is Active!'));
app.listen(PORT, () => console.log(`Server running on port ${PORT}`));

const bot = new TelegramBot(TELEGRAM_TOKEN, { polling: true });

bot.on('polling_error', (error) => {
    if (error.code === 'ETELEGRAM' && error.message.includes('409 Conflict')) {
        console.error('CRITICAL: Multi-instance Conflict!');
    }
});

const userSockets = {};
const userStates = {};
const authenticatedUsers = new Set(); 

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

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
    const { version } = await fetchLatestBaileysVersion();

    const waSock = makeWASocket({
        version,
        auth: state,
        printQRInTerminal: false,
        browser: Browsers.ubuntu('Chrome'), // Ubuntu Chrome Agent use kora hoyeche pairing issue bypass korar jonno
        markOnlineOnConnect: false,
        syncFullHistory: false
    });

    waSock.ev.on('creds.update', saveCreds);
    
    waSock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect } = update;
        
        if (connection === 'open') {
            bot.sendMessage(chatId, "✅ **WhatsApp successfully connected!**\n\nEhbar '📱 Check Number' batane click kore number check korun.", {
                parse_mode: "Markdown",
                reply_markup: getMainButtons()
            });
        } else if (connection === 'close') {
            delete userSockets[chatId];
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            const shouldReconnect = statusCode !== disconnectReason.loggedOut;
            if (shouldReconnect) {
                getUserSocket(chatId);
            } else {
                // Session clean up if logged out
                try { fs.rmSync(sessionDir, { recursive: true, force: true }); } catch (e) {}
            }
        }
    });

    userSockets[chatId] = waSock;
    return waSock;
}

bot.onText(/\/start/, (msg) => {
    const chatId = msg.chat.id;

    if (msg.from.id === ADMIN_ID) {
        authenticatedUsers.add(chatId);
        return bot.sendMessage(chatId, "👑 **Admin Panel!**\n\nPassword change korar jonno likhun: `/setpass new_password`", {
            parse_mode: "Markdown",
            reply_markup: getMainButtons()
        });
    }

    if (authenticatedUsers.has(chatId)) {
        bot.sendMessage(chatId, "👋 Welcome! Nicher batan theke option select korun:", {
            parse_mode: "Markdown",
            reply_markup: getMainButtons()
        });
    } else {
        userStates[chatId] = "WAITING_FOR_PASSWORD";
        bot.sendMessage(chatId, "🔒 **Password required.**\n\nDoya kore password ti pathan:");
    }
});

bot.onText(/\/setpass (.+)/, (msg, match) => {
    const chatId = msg.chat.id;

    if (msg.from.id !== ADMIN_ID) {
        return bot.sendMessage(chatId, "⚠️ Sudhu admin password change korte parbe.");
    }

    const newPass = match[1].trim();
    currentPassword = newPass;
    bot.sendMessage(chatId, `✅ Notun password set kora hoyeche: \`${newPass}\``, { parse_mode: "Markdown" });
});

bot.on('callback_query', async (query) => {
    const chatId = query.message.chat.id;
    const action = query.data;

    bot.answerCallbackQuery(query.id);

    if (!authenticatedUsers.has(chatId) && query.from.id !== ADMIN_ID) {
        userStates[chatId] = "WAITING_FOR_PASSWORD";
        return bot.sendMessage(chatId, "🔒 Doya kore prothome sothik password diye login korun.");
    }

    if (action === "cmd_link") {
        userStates[chatId] = "WAITING_FOR_LINK_NUMBER";
        bot.sendMessage(chatId, "📲 **Apnar WhatsApp number-ti din** (Country code soho, jemon: `8801700000000`):", { parse_mode: "Markdown" });

    } else if (action === "cmd_check") {
        const waSock = userSockets[chatId];
        if (!waSock || !waSock.authState?.creds?.registered) {
            return bot.sendMessage(chatId, "⚠️ **Apnar WhatsApp connect kora nei!**\n\nProthome '🔗 Link WhatsApp' batane click korun.", {
                reply_markup: getMainButtons()
            });
        }
        userStates[chatId] = "WAITING_FOR_CHECK_NUMBER";
        bot.sendMessage(chatId, "🔍 **Jey number-ti check korte chan seti pathan** (jemon: `8801800000000`):", { parse_mode: "Markdown" });

    } else if (action === "cmd_help") {
        const isConnected = userSockets[chatId]?.authState?.creds?.registered ? "✅ Connected" : "❌ Not Connected";
        bot.sendMessage(chatId, `ℹ️ **Bot Status:**\n- WhatsApp Status: ${isConnected}`, {
            reply_markup: getMainButtons()
        });
    }
});

bot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    const text = msg.text?.trim();

    if (!text || text.startsWith('/')) return;

    if (!authenticatedUsers.has(chatId) && msg.from.id !== ADMIN_ID) {
        if (text === currentPassword) {
            authenticatedUsers.add(chatId);
            delete userStates[chatId];
            return bot.sendMessage(chatId, "🎉 **Password sothik hoyeche!**\n\nNicher batan theke option select korun:", {
                parse_mode: "Markdown",
                reply_markup: getMainButtons()
            });
        } else {
            return bot.sendMessage(chatId, "❌ **Bhul password!** Abar chesta korun:");
        }
    }

    const state = userStates[chatId];

    if (state === "WAITING_FOR_LINK_NUMBER") {
        delete userStates[chatId];
        const phone = text.replace('+', '').replace(/\s+/g, '');

        if (isNaN(phone) || phone.length < 10) {
            return bot.sendMessage(chatId, "❌ Sothik number din. Udahoron: `8801700000000`", { reply_markup: getMainButtons() });
        }

        bot.sendMessage(chatId, "⏳ Pairing Code toiri kora hocche...");

        try {
            const waSock = await getUserSocket(chatId);
            await delay(3000);

            let code = await waSock.requestPairingCode(phone);
            code = code?.match(/.{1,4}/g)?.join("-") || code;

            bot.sendMessage(chatId, `🔑 **Apnar Pairing Code:** \`${code}\`\n\nWhatsApp > Linked Devices > Link with phone number-e **druto (1 minute-er moddhe)** eii code-ti boshan.`, {
                parse_mode: "Markdown",
                reply_markup: getMainButtons()
            });
        } catch (err) {
            console.error("Pairing Error:", err);
            bot.sendMessage(chatId, "❌ Code generate hote somossha hoyeche. Abar chesta korun.", { reply_markup: getMainButtons() });
        }

    } else if (state === "WAITING_FOR_CHECK_NUMBER") {
        delete userStates[chatId];
        const waSock = userSockets[chatId];

        if (!waSock || !waSock.authState?.creds?.registered) {
            return bot.sendMessage(chatId, "⚠️ Apnar WhatsApp connect kora nei!", { reply_markup: getMainButtons() });
        }

        const checkPhone = text.replace('+', '').replace(/[^0-9]/g, '');
        if (!checkPhone || isNaN(checkPhone)) return bot.sendMessage(chatId, "❌ Sothik number din.", { reply_markup: getMainButtons() });

        bot.sendMessage(chatId, `⏳ \`+${checkPhone}\` number-ti check kora hocche...`, { parse_mode: "Markdown" });

        try {
            await delay(1000);
            const [result] = await waSock.onWhatsApp(checkPhone);

            if (result && result.exists) {
                bot.sendMessage(chatId, `📱 Number: +${checkPhone}\n❌ **LOGIN NOT AVAILABLE** (Account khola ache)`, { reply_markup: getMainButtons() });
            } else {
                bot.sendMessage(chatId, `📱 Number: +${checkPhone}\n✅ **FRESH / HIGH OTP RATE** (Notun account, OTP asbe)`, { reply_markup: getMainButtons() });
            }
        } catch (error) {
            console.error("Check Error:", error);
            bot.sendMessage(chatId, "❌ Check korte somossha hoyeche.", { reply_markup: getMainButtons() });
        }
    }
});
            
