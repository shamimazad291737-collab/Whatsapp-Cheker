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

// 1. Configuration
const TELEGRAM_TOKEN = process.env.TELEGRAM_TOKEN; 
const ADMIN_ID = 7388500439; 
let currentPassword = "291736"; 

if (!TELEGRAM_TOKEN) {
    console.error("CRITICAL ERROR: TELEGRAM_TOKEN missing!");
    process.exit(1);
}

// Keep-alive server
const app = express();
const PORT = process.env.PORT || 3000;
app.get('/', (req, res) => res.send('WhatsApp Checker active!'));
app.listen(PORT, () => console.log(`Server on port ${PORT}`));

const bot = new TelegramBot(TELEGRAM_TOKEN, { polling: true });

// Multi-instance & crash prevention
bot.on('polling_error', (err) => {
    if (err.message.includes('409 Conflict')) {
        console.error('Multi-instance conflict! Change token or stop other instance.');
    }
});

process.on('uncaughtException', (err) => console.error('Uncaught Exception:', err));
process.on('unhandledRejection', (reason) => console.error('Unhandled Rejection:', reason));

const userSockets = {};
const userStates = {};
const authenticatedUsers = new Set(); 

const delay = (ms) => new Promise((res) => setTimeout(res, ms));

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

// Fixed WhatsApp Connection Handler
async function getUserSocket(chatId) {
    if (userSockets[chatId]) return userSockets[chatId];

    const sessionDir = path.join(__dirname, 'sessions', `session_${chatId}`);
    if (!fs.existsSync(sessionDir)) {
        fs.mkdirSync(sessionDir, { recursive: true });
    }

    const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
    
    // Fetch actual latest version
    let version = [2, 3000, 1015901307];
    try {
        const fetchRes = await fetchLatestBaileysVersion();
        version = fetchRes.version;
    } catch (e) {
        console.log("Using fallback Baileys version");
    }

    const waSock = makeWASocket({
        version,
        logger: pino({ level: 'fatal' }),
        printQRInTerminal: false,
        // Crucial Fix: macOS / Safari browser config stops "Logging in..." hanging
        browser: Browsers.macOS('Desktop'),
        auth: {
            creds: state.creds,
            keys: makeCacheableSignalKeyStore(state.keys, pino({ level: 'fatal' }))
        },
        markOnlineOnConnect: true,
        generateHighQualityLinkPreview: false,
        syncFullHistory: false,
        retryRequestOptions: {
            delayMs: 2000,
            maxRetries: 5
        }
    });

    waSock.ev.on('creds.update', saveCreds);

    waSock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect } = update;

        if (connection === 'open') {
            bot.sendMessage(chatId, "✅ **WhatsApp-e Safollo-bhabe Connect Hoyeche!**\n\nEhbar '📱 Check Number' batan click kore number filter korun.", {
                parse_mode: "Markdown",
                reply_markup: getMainButtons()
            });
        } else if (connection === 'close') {
            delete userSockets[chatId];
            const reason = lastDisconnect?.error?.output?.statusCode;
            
            if (reason !== DisconnectReason.loggedOut) {
                console.log(`Reconnecting for ${chatId}... Reason:${reason}`);
                await delay(3000);
                getUserSocket(chatId);
            } else {
                console.log(`Logged out ${chatId}. Cleaning session...`);
                try { fs.rmSync(sessionDir, { recursive: true, force: true }); } catch (e) {}
            }
        }
    });

    userSockets[chatId] = waSock;
    return waSock;
}

// Start Command
bot.onText(/\/start/, (msg) => {
    const chatId = msg.chat.id;

    if (msg.from.id === ADMIN_ID) {
        authenticatedUsers.add(chatId);
        return bot.sendMessage(chatId, "👑 **Admin Mode Activated**", {
            parse_mode: "Markdown",
            reply_markup: getMainButtons()
        });
    }

    if (authenticatedUsers.has(chatId)) {
        bot.sendMessage(chatId, "👋 Welcome back!", { reply_markup: getMainButtons() });
    } else {
        userStates[chatId] = "WAITING_FOR_PASSWORD";
        bot.sendMessage(chatId, "🔒 **Password Required!**\n\nDoya kore password din:");
    }
});

// Admin Password Change
bot.onText(/\/setpass (.+)/, (msg, match) => {
    if (msg.from.id !== ADMIN_ID) return;
    currentPassword = match[1].trim();
    bot.sendMessage(msg.chat.id, `✅ Notun password: \`${currentPassword}\``, { parse_mode: "Markdown" });
});

// Buttons Action
bot.on('callback_query', async (query) => {
    const chatId = query.message.chat.id;
    const action = query.data;

    bot.answerCallbackQuery(query.id);

    if (!authenticatedUsers.has(chatId) && query.from.id !== ADMIN_ID) {
        userStates[chatId] = "WAITING_FOR_PASSWORD";
        return bot.sendMessage(chatId, "🔒 Prothome password din.");
    }

    if (action === "cmd_link") {
        userStates[chatId] = "WAITING_FOR_LINK_NUMBER";
        bot.sendMessage(chatId, "📲 Country code সহ apnar WhatsApp number din (e.g. `8801700000000`):", { parse_mode: "Markdown" });

    } else if (action === "cmd_check") {
        const waSock = userSockets[chatId];
        if (!waSock || !waSock.authState?.creds?.registered) {
            return bot.sendMessage(chatId, "⚠️ Prothome WhatsApp link korun!", { reply_markup: getMainButtons() });
        }
        userStates[chatId] = "WAITING_FOR_CHECK_NUMBER";
        bot.sendMessage(chatId, "🔍 Jey number check korben seti din (e.g. `8801800000000`):", { parse_mode: "Markdown" });

    } else if (action === "cmd_help") {
        const isConnected = userSockets[chatId]?.authState?.creds?.registered ? "✅ Connected" : "❌ Not Connected";
        bot.sendMessage(chatId, `ℹ️ **Bot Status:** ${isConnected}`, { reply_markup: getMainButtons() });
    }
});

// Main Message Processor
bot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    const text = msg.text?.trim();

    if (!text || text.startsWith('/')) return;

    // Password Check
    if (!authenticatedUsers.has(chatId) && msg.from.id !== ADMIN_ID) {
        if (text === currentPassword) {
            authenticatedUsers.add(chatId);
            delete userStates[chatId];
            return bot.sendMessage(chatId, "🎉 Access Granted!", { reply_markup: getMainButtons() });
        } else {
            return bot.sendMessage(chatId, "❌ Bhul Password!");
        }
    }

    const state = userStates[chatId];

    // Pairing Request
    if (state === "WAITING_FOR_LINK_NUMBER") {
        delete userStates[chatId];
        const phone = text.replace(/[^0-9]/g, '');

        if (phone.length < 10) {
            return bot.sendMessage(chatId, "❌ Invalid Number!", { reply_markup: getMainButtons() });
        }

        bot.sendMessage(chatId, "⏳ Pairing code toiri hocche...");

        try {
            const waSock = await getUserSocket(chatId);
            await delay(4000); // Allow WebSocket handshake to complete fully

            let code = await waSock.requestPairingCode(phone);
            code = code?.match(/.{1,4}/g)?.join("-") || code;

            bot.sendMessage(chatId, `🔑 **Pairing Code:** \`${code}\`\n\nWhatsApp > Linked Devices > Link with phone number-e boshān.`, {
                parse_mode: "Markdown",
                reply_markup: getMainButtons()
            });
        } catch (err) {
            console.error("Pairing Error:", err);
            bot.sendMessage(chatId, "❌ Pairing fail hoyeche. Abar chesta korun.", { reply_markup: getMainButtons() });
        }

    // Number Check Logic
    } else if (state === "WAITING_FOR_CHECK_NUMBER") {
        delete userStates[chatId];
        const waSock = userSockets[chatId];

        if (!waSock || !waSock.authState?.creds?.registered) {
            return bot.sendMessage(chatId, "⚠️ WhatsApp connect kora nei!", { reply_markup: getMainButtons() });
        }

        const checkPhone = text.replace(/[^0-9]/g, '');
        if (!checkPhone) return bot.sendMessage(chatId, "❌ Sothik number din.", { reply_markup: getMainButtons() });

        const jid = `${checkPhone}@s.whatsapp.net`;
        bot.sendMessage(chatId, `⏳ \`+${checkPhone}\` check kora hocche...`, { parse_mode: "Markdown" });

        try {
            await delay(1000);
            const [result] = await waSock.onWhatsApp(checkPhone);

            if (!result || !result.exists) {
                const report = `📱 **Number:** \`+${checkPhone}\`\n` +
                               `STATUS: ✅ **FRESH NUMBER**\n` +
                               `Send Success Rate: **95%**\n` +
                               `Condition: **No Active WhatsApp Account**`;
                
                bot.sendMessage(chatId, report, { parse_mode: "Markdown", reply_markup: getMainButtons() });
            } else {
                let profilePic = null;
                let statusBio = null;

                try { profilePic = await waSock.profilePictureUrl(jid, 'image'); } catch (e) {}
                try { statusBio = await waSock.fetchStatus(jid); } catch (e) {}

                let statusText = "";
                let sendRate = "";

                if (!profilePic && !statusBio) {
                    statusText = "⚠️ **SEMI-FRESH (No DP/Bio)**";
                    sendRate = "**75%**";
                } else {
                    statusText = "❌ **LOGIN NOT AVAILABLE (Active Account)**";
                    sendRate = "**20%**";
                }

                const report = `📱 **Number:** \`+${checkPhone}\`\n` +
                               `STATUS: ${statusText}\n` +
                               `Send/Delivery Chance: ${sendRate}\n` +
                               `Bio: \`${statusBio?.status || "None"}\``;

                bot.sendMessage(chatId, report, { parse_mode: "Markdown", reply_markup: getMainButtons() });
            }
        } catch (error) {
            console.error("Check Error:", error);
            bot.sendMessage(chatId, "❌ Check fail hoyeche.", { reply_markup: getMainButtons() });
        }
    }
});
        
