const { default: makeWASocket, useMultiFileAuthState, disconnectReason, fetchLatestBaileysVersion, Browsers } = require('@whiskeysockets/baileys');
const TelegramBot = require('node-telegram-bot-api');
const express = require('express');
const fs = require('fs');

// 1. Configuration (Render Environment Variable)
const TELEGRAM_TOKEN = process.env.TELEGRAM_TOKEN; 
const ADMIN_ID = 7388500439; 
let currentPassword = "291736"; 

if (!TELEGRAM_TOKEN) {
    console.error("CRITICAL ERROR: TELEGRAM_TOKEN missing in Render Environment Variables!");
    process.exit(1);
}

// Express Keep-Alive Web Server for Render
const app = express();
const PORT = process.env.PORT || 3000;
app.get('/', (req, res) => res.send('WhatsApp Checker Bot is Running Smoothly!'));
app.listen(PORT, () => console.log(`Server running on port ${PORT}`));

const bot = new TelegramBot(TELEGRAM_TOKEN, { polling: true });

// Prevent Unhandled Error Crashing (Status 1 Exit fix)
bot.on('polling_error', (error) => {
    if (error.code === 'ETELEGRAM' && error.message.includes('409 Conflict')) {
        console.error('CRITICAL: Multi-instance Conflict! Make sure only 1 instance is running.');
    } else {
        console.error('Polling error:', error.message);
    }
});

process.on('uncaughtException', (err) => {
    console.error('Uncaught Exception caught to prevent crash:', err);
});

process.on('unhandledRejection', (reason, promise) => {
    console.error('Unhandled Rejection caught to prevent crash:', reason);
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
    
    // Latest Baileys Version fetch to fix pairing stuck issue
    let version;
    try {
        const fetchRes = await fetchLatestBaileysVersion();
        version = fetchRes.version;
    } catch (e) {
        version = [2, 3000, 1015901307];
    }

    const waSock = makeWASocket({
        version,
        auth: state,
        printQRInTerminal: false,
        browser: Browsers.ubuntu('Chrome'), // Fixes 'Couldn't link device' & 'Logging in stuck'
        keepAliveIntervalMs: 30000,
        connectTimeoutMs: 60000,
        defaultQueryTimeoutMs: 60000,
        syncFullHistory: false
    });

    waSock.ev.on('creds.update', saveCreds);
    
    waSock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect } = update;
        
        if (connection === 'open') {
            bot.sendMessage(chatId, "✅ **WhatsApp successfully connected!**\n\nEhbar '📱 Check Number' batane click kore number filtering shuru korun.", {
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
                try { fs.rmSync(sessionDir, { recursive: true, force: true }); } catch (e) {}
            }
        }
    });

    userSockets[chatId] = waSock;
    return waSock;
}

// /start command
bot.onText(/\/start/, (msg) => {
    const chatId = msg.chat.id;

    if (msg.from.id === ADMIN_ID) {
        authenticatedUsers.add(chatId);
        return bot.sendMessage(chatId, "👑 **Admin Dashboard Active!**\n\nPassword change korar jonno: `/setpass notun_password`", {
            parse_mode: "Markdown",
            reply_markup: getMainButtons()
        });
    }

    if (authenticatedUsers.has(chatId)) {
        bot.sendMessage(chatId, "👋 Welcome back! Nicher menu theke option select korun:", {
            parse_mode: "Markdown",
            reply_markup: getMainButtons()
        });
    } else {
        userStates[chatId] = "WAITING_FOR_PASSWORD";
        bot.sendMessage(chatId, "🔒 **Password Required!**\n\nDoya kore bot-er password-ti din:");
    }
});

// Admin Password Update Command
bot.onText(/\/setpass (.+)/, (msg, match) => {
    const chatId = msg.chat.id;

    if (msg.from.id !== ADMIN_ID) {
        return bot.sendMessage(chatId, "⚠️ Sudhu Admin password change korte parbe.");
    }

    const newPass = match[1].trim();
    currentPassword = newPass;
    bot.sendMessage(chatId, `✅ Notun password set hoyeche: \`${newPass}\``, { parse_mode: "Markdown" });
});

// Callback Query Handler
bot.on('callback_query', async (query) => {
    const chatId = query.message.chat.id;
    const action = query.data;

    bot.answerCallbackQuery(query.id);

    if (!authenticatedUsers.has(chatId) && query.from.id !== ADMIN_ID) {
        userStates[chatId] = "WAITING_FOR_PASSWORD";
        return bot.sendMessage(chatId, "🔒 Doya kore prothome password diye access nin.");
    }

    if (action === "cmd_link") {
        userStates[chatId] = "WAITING_FOR_LINK_NUMBER";
        bot.sendMessage(chatId, "📲 **Apnar WhatsApp number-ti din** (Country code soho, e.g., `8801700000000`):", { parse_mode: "Markdown" });

    } else if (action === "cmd_check") {
        const waSock = userSockets[chatId];
        if (!waSock || !waSock.authState?.creds?.registered) {
            return bot.sendMessage(chatId, "⚠️ **Apnar WhatsApp connect kora nei!**\n\nProthome '🔗 Link WhatsApp' batane click korun.", {
                reply_markup: getMainButtons()
            });
        }
        userStates[chatId] = "WAITING_FOR_CHECK_NUMBER";
        bot.sendMessage(chatId, "🔍 **Jey number-ti check korte chan seti pathan** (e.g., `8801800000000`):", { parse_mode: "Markdown" });

    } else if (action === "cmd_help") {
        const isConnected = userSockets[chatId]?.authState?.creds?.registered ? "✅ Connected" : "❌ Not Connected";
        bot.sendMessage(chatId, `ℹ️ **Bot Status:**\n- WhatsApp Status: ${isConnected}`, {
            reply_markup: getMainButtons()
        });
    }
});

// Main Message Receiver & Checker Logic
bot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    const text = msg.text?.trim();

    if (!text || text.startsWith('/')) return;

    // Password Verification
    if (!authenticatedUsers.has(chatId) && msg.from.id !== ADMIN_ID) {
        if (text === currentPassword) {
            authenticatedUsers.add(chatId);
            delete userStates[chatId];
            return bot.sendMessage(chatId, "🎉 **Password Sothik Hoyeche!**\n\nNicher button theke option select korun:", {
                parse_mode: "Markdown",
                reply_markup: getMainButtons()
            });
        } else {
            return bot.sendMessage(chatId, "❌ **Bhul Password!** Abar chesta korun:");
        }
    }

    const state = userStates[chatId];

    // WhatsApp Link Handler
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

            bot.sendMessage(chatId, `🔑 **Apnar Pairing Code:** \`${code}\`\n\nWhatsApp > Linked Devices > Link with phone number-e druto eii code-ti boshan.`, {
                parse_mode: "Markdown",
                reply_markup: getMainButtons()
            });
        } catch (err) {
            console.error("Pairing Request Error:", err);
            bot.sendMessage(chatId, "❌ Code generate hote problem hoyeche. Abar chesta korun.", { reply_markup: getMainButtons() });
        }

    // Advanced Number Check Handler
    } else if (state === "WAITING_FOR_CHECK_NUMBER") {
        delete userStates[chatId];
        const waSock = userSockets[chatId];

        if (!waSock || !waSock.authState?.creds?.registered) {
            return bot.sendMessage(chatId, "⚠️ Apnar WhatsApp connect kora nei!", { reply_markup: getMainButtons() });
        }

        const checkPhone = text.replace('+', '').replace(/[^0-9]/g, '');
        if (!checkPhone || isNaN(checkPhone)) return bot.sendMessage(chatId, "❌ Sothik number din.", { reply_markup: getMainButtons() });

        const jid = `${checkPhone}@s.whatsapp.net`;
        bot.sendMessage(chatId, `⏳ \`+${checkPhone}\` number-er details check kora hocche...`, { parse_mode: "Markdown" });

        try {
            await delay(1000);
            const [result] = await waSock.onWhatsApp(checkPhone);

            if (!result || !result.exists) {
                // Number Fresh / Not Registered on WhatsApp
                const report = `📱 **Number:** \`+${checkPhone}\`\n` +
                               `STATUS: ✅ **FRESH NUMBER**\n` +
                               `OTP Send Chance: **95%** (High Success Rate)\n` +
                               `Account Condition: **No WhatsApp Account Found**`;
                
                bot.sendMessage(chatId, report, { parse_mode: "Markdown", reply_markup: getMainButtons() });
            } else {
                // Registered WhatsApp Account -> Deep Check (Bio / Picture)
                let profilePic = null;
                let statusBio = null;

                try { profilePic = await waSock.profilePictureUrl(jid, 'image'); } catch (e) {}
                try { statusBio = await waSock.fetchStatus(jid); } catch (e) {}

                let accountType = "";
                let codeChance = "";

                if (!profilePic && !statusBio) {
                    accountType = "⚠️ **NEW / SEMI-FRESH ACCOUNT** (No DP/Bio)";
                    codeChance = "**75%** (Medium-High)";
                } else {
                    accountType = "❌ **LOGIN NOT AVAILABLE** (Active/Old Account)";
                    codeChance = "**25%** (Low Chance for New Login/OTP)";
                }

                const report = `📱 **Number:** \`+${checkPhone}\`\n` +
                               `STATUS: ${accountType}\n` +
                               `Code Send / OTP Success Rate: ${codeChance}\n` +
                               `Bio Status: \`${statusBio?.status || "None"}\``;

                bot.sendMessage(chatId, report, { parse_mode: "Markdown", reply_markup: getMainButtons() });
            }
        } catch (error) {
            console.error("Check Execution Error:", error);
            bot.sendMessage(chatId, "❌ Check korte problem hoyeche. WhatsApp session active ache kina check korun.", { reply_markup: getMainButtons() });
        }
    }
});
            
