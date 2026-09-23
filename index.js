const { 
    default: makeWASocket, 
    useMultiFileAuthState, 
    DisconnectReason, 
    fetchLatestBaileysVersion, 
    Browsers,
    makeCacheableSignalKeyStore
} = require('@whiskeysockets/baileys');
const TelegramBot = require('node-telegram-bot-api');
const express = require('express');
const fs = require('fs');
const path = require('path');
const pino = require('pino');

const TELEGRAM_TOKEN = process.env.TELEGRAM_TOKEN; 
const ADMIN_ID = 7388500439; 
let currentPassword = "291736"; 

if (!TELEGRAM_TOKEN) {
    console.error("CRITICAL ERROR: TELEGRAM_TOKEN missing!");
    process.exit(1);
}

// Keep-alive Express Server
const app = express();
const PORT = process.env.PORT || 10000;
app.get('/', (req, res) => res.status(200).send('WhatsApp Checker Active!'));
app.listen(PORT, '0.0.0.0', () => console.log(`Server running on port ${PORT}`));

// Polling auto-restart & error suppression
const bot = new TelegramBot(TELEGRAM_TOKEN, { polling: true });

bot.on('polling_error', (err) => {
    if (err.message.includes('409 Conflict')) {
        console.log('Duplicate polling handled.');
    }
});

process.on('uncaughtException', (err) => console.error('Uncaught Exception:', err));
process.on('unhandledRejection', (reason) => console.error('Unhandled Rejection:', reason));

const userSockets = {};
const userStates = {};
const authenticatedUsers = new Set(); 
const connectionNotified = {}; 

function getMainReplyKeyboard() {
    return {
        keyboard: [
            [{ text: "🔢 Pair via Code" }],
            [{ text: "📱 Check Number" }, { text: "ℹ️ Help & Status" }]
        ],
        resize_keyboard: true
    };
}

// Safe Session Folder Creator
function ensureDirExists(dirPath) {
    if (!fs.existsSync(dirPath)) {
        fs.mkdirSync(dirPath, { recursive: true });
    }
}

async function getUserSocket(chatId, forceReset = false) {
    const baseSessionsDir = path.join(process.cwd(), 'sessions');
    ensureDirExists(baseSessionsDir);
    
    const sessionDir = path.join(baseSessionsDir, `session_${chatId}`);
    
    if (forceReset) {
        if (userSockets[chatId]) {
            try { userSockets[chatId].end(undefined); } catch (e) {}
            delete userSockets[chatId];
        }
        if (fs.existsSync(sessionDir)) {
            try { fs.rmSync(sessionDir, { recursive: true, force: true }); } catch (e) {}
        }
    } else if (userSockets[chatId]) {
        return userSockets[chatId];
    }

    ensureDirExists(sessionDir);

    const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
    
    let version = [2, 3000, 1015901307];
    try {
        const fetchRes = await fetchLatestBaileysVersion();
        version = fetchRes.version;
    } catch (e) {}

    const waSock = makeWASocket({
        version,
        logger: pino({ level: 'fatal' }),
        printQRInTerminal: false,
        browser: Browsers.ubuntu('Chrome'),
        auth: {
            creds: state.creds,
            keys: makeCacheableSignalKeyStore(state.keys, pino({ level: 'fatal' }))
        },
        markOnlineOnConnect: true,
        generateHighQualityLinkPreview: false,
        syncFullHistory: false,
        connectTimeoutMs: 60000,
        defaultQueryTimeoutMs: 0,
        keepAliveIntervalMs: 10000
    });

    waSock.ev.on('creds.update', saveCreds);

    waSock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect } = update;

        if (connection === 'open') {
            if (!connectionNotified[chatId]) {
                connectionNotified[chatId] = true;
                bot.sendMessage(chatId, "🎉 **WhatsApp Connected Successfully!**\n\nEhbar **📱 Check Number** option use koren.", {
                    parse_mode: "Markdown",
                    reply_markup: getMainReplyKeyboard()
                });
            }
        } else if (connection === 'close') {
            connectionNotified[chatId] = false;
            delete userSockets[chatId];
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            if (statusCode === DisconnectReason.loggedOut) {
                try { fs.rmSync(sessionDir, { recursive: true, force: true }); } catch (e) {}
            }
        }
    });

    userSockets[chatId] = waSock;
    return waSock;
}

// Bot Commands
bot.onText(/\/(start|strat|help)/i, (msg) => {
    const chatId = msg.chat.id;
    if (msg.from.id === ADMIN_ID || authenticatedUsers.has(chatId)) {
        authenticatedUsers.add(chatId);
        bot.sendMessage(chatId, "👋 **WhatsApp Checker Control Panel:**", {
            parse_mode: "Markdown",
            reply_markup: getMainReplyKeyboard()
        });
    } else {
        userStates[chatId] = "WAITING_FOR_PASSWORD";
        bot.sendMessage(chatId, "🔒 **Password Required!** Doya kore password din:");
    }
});

// Messages Handler
bot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    const text = msg.text?.trim();

    if (!text || text.startsWith('/')) return;

    if (!authenticatedUsers.has(chatId) && msg.from.id !== ADMIN_ID) {
        if (text === currentPassword) {
            authenticatedUsers.add(chatId);
            delete userStates[chatId];
            return bot.sendMessage(chatId, "🎉 Access Granted!", { reply_markup: getMainReplyKeyboard() });
        } else {
            return bot.sendMessage(chatId, "❌ Bhul Password!");
        }
    }

    if (text === "🔢 Pair via Code") {
        userStates[chatId] = "WAITING_FOR_LINK_NUMBER";
        return bot.sendMessage(chatId, "📲 Apnar WhatsApp number-ti din (Country code sho, e.g. `8801700000000`):", { parse_mode: "Markdown" });
    } 
    
    if (text === "📱 Check Number") {
        const waSock = userSockets[chatId];
        const isConnected = waSock && (waSock.user || waSock.authState?.creds?.me || waSock.authState?.creds?.registered);

        if (!isConnected) {
            return bot.sendMessage(chatId, "⚠️ Prothome **🔢 Pair via Code** diye WhatsApp connect korun!", { reply_markup: getMainReplyKeyboard() });
        }
        userStates[chatId] = "WAITING_FOR_CHECK_NUMBER";
        return bot.sendMessage(chatId, "🔍 Jey number check korben seti din (e.g. `8801800000000`):", { parse_mode: "Markdown" });
    } 

    if (text === "ℹ️ Help & Status") {
        const waSock = userSockets[chatId];
        const isConnected = waSock && (waSock.user || waSock.authState?.creds?.me || waSock.authState?.creds?.registered) ? "✅ Connected" : "❌ Not Connected";
        return bot.sendMessage(chatId, `ℹ️ **Bot Status:** ${isConnected}`, { reply_markup: getMainReplyKeyboard() });
    }

    const state = userStates[chatId];

    if (state === "WAITING_FOR_LINK_NUMBER") {
        delete userStates[chatId];
        const phone = text.replace(/[^0-9]/g, '');

        bot.sendMessage(chatId, "⏳ Pairing session ready hocche...");

        try {
            const waSock = await getUserSocket(chatId, true);
            
            // Wait for socket initiation
            await new Promise((res) => setTimeout(res, 3000));

            let code = await waSock.requestPairingCode(phone);
            code = code?.match(/.{1,4}/g)?.join("-") || code;

            bot.sendMessage(chatId, `🔑 **Pairing Code:** \`${code}\`\n\n👉 Apnar WhatsApp > Linked Devices > Link with Phone Number-e giye eii code bosiye din!`, {
                parse_mode: "Markdown",
                reply_markup: getMainReplyKeyboard()
            });
        } catch (err) {
            console.error("Pairing Code Error:", err);
            bot.sendMessage(chatId, "❌ Pairing fail hoyeche! Abar try koren.", { reply_markup: getMainReplyKeyboard() });
        }

    } else if (state === "WAITING_FOR_CHECK_NUMBER") {
        delete userStates[chatId];
        const waSock = userSockets[chatId];

        if (!waSock) {
            return bot.sendMessage(chatId, "⚠️ WhatsApp connect kora nei!", { reply_markup: getMainReplyKeyboard() });
        }

        const checkPhone = text.replace(/[^0-9]/g, '');
        const jid = `${checkPhone}@s.whatsapp.net`;
        bot.sendMessage(chatId, `⏳ \`+${checkPhone}\` checking...`, { parse_mode: "Markdown" });

        try {
            const [result] = await waSock.onWhatsApp(checkPhone);

            if (!result || !result.exists) {
                bot.sendMessage(chatId, `📱 **Number:** \`+${checkPhone}\`\nSTATUS: ✅ **FRESH NUMBER**\nSend Success Chance: **95%**`, { parse_mode: "Markdown", reply_markup: getMainReplyKeyboard() });
            } else {
                let profilePic = null, statusBio = null;
                try { profilePic = await waSock.profilePictureUrl(jid, 'image'); } catch (e) {}
                try { statusBio = await waSock.fetchStatus(jid); } catch (e) {}

                let statusText = (!profilePic && !statusBio) ? "⚠️ **SEMI-FRESH (75% Delivery Rate)**" : "❌ **ACTIVE WHATSAPP ACCOUNT**";

                bot.sendMessage(chatId, `📱 **Number:** \`+${checkPhone}\`\nSTATUS: ${statusText}\nBio: \`${statusBio?.status || "None"}\``, { parse_mode: "Markdown", reply_markup: getMainReplyKeyboard() });
            }
        } catch (error) {
            bot.sendMessage(chatId, "❌ Check failed.", { reply_markup: getMainReplyKeyboard() });
        }
    }
});
                    
