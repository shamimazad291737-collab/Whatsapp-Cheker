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
const QRCode = require('qrcode');

const TELEGRAM_TOKEN = process.env.TELEGRAM_TOKEN; 
const ADMIN_ID = 7388500439; 
let currentPassword = "291736"; 

if (!TELEGRAM_TOKEN) {
    console.error("CRITICAL ERROR: TELEGRAM_TOKEN missing!");
    process.exit(1);
}

const app = express();
const PORT = process.env.PORT || 3000;
app.get('/', (req, res) => res.send('WhatsApp Checker Active!'));
app.listen(PORT, () => console.log(`Server running on port ${PORT}`));

const bot = new TelegramBot(TELEGRAM_TOKEN, { polling: true });

bot.on('polling_error', (err) => {
    if (err.message.includes('409 Conflict')) {
        console.error('Multi-instance conflict detected!');
    }
});

process.on('uncaughtException', (err) => console.error('Uncaught Exception:', err));
process.on('unhandledRejection', (reason) => console.error('Unhandled Rejection:', reason));

const userSockets = {};
const userStates = {};
const authenticatedUsers = new Set(); 
const connectionNotified = {}; // Loop message prevention flag

function getMainButtons() {
    return {
        inline_keyboard: [
            [
                { text: "📷 Scan QR Code (Fast Link)", callback_data: "cmd_qr_link" },
                { text: "🔢 Pair via Code", callback_data: "cmd_link" }
            ],
            [
                { text: "📱 Check Number", callback_data: "cmd_check" },
                { text: "ℹ️ Help & Status", callback_data: "cmd_help" }
            ]
        ]
    };
}

async function getUserSocket(chatId, forceQR = false) {
    if (userSockets[chatId] && !forceQR) return userSockets[chatId];

    const sessionDir = path.join(__dirname, 'sessions', `session_${chatId}`);
    if (!fs.existsSync(sessionDir)) {
        fs.mkdirSync(sessionDir, { recursive: true });
    }

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
        browser: Browsers.macOS('Desktop'),
        auth: {
            creds: state.creds,
            keys: makeCacheableSignalKeyStore(state.keys, pino({ level: 'fatal' }))
        },
        markOnlineOnConnect: true,
        generateHighQualityLinkPreview: false,
        syncFullHistory: false
    });

    waSock.ev.on('creds.update', saveCreds);

    waSock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr && forceQR) {
            try {
                const qrImagePath = path.join(__dirname, `qr_${chatId}.png`);
                await QRCode.toFile(qrImagePath, qr);
                await bot.sendPhoto(chatId, qrImagePath, {
                    caption: "📸 **WhatsApp > Linked Devices > Link a Device** e giye eii QR code ti scan korun!"
                });
                if (fs.existsSync(qrImagePath)) fs.unlinkSync(qrImagePath);
            } catch (qrErr) {
                console.error("QR Generate Error:", qrErr);
            }
        }

        if (connection === 'open') {
            if (!connectionNotified[chatId]) {
                connectionNotified[chatId] = true;
                bot.sendMessage(chatId, "✅ **WhatsApp Connection Successful!**\n\nEhbar '📱 Check Number' e click kore number check korun.", {
                    parse_mode: "Markdown",
                    reply_markup: getMainButtons()
                });
            }
        } else if (connection === 'close') {
            connectionNotified[chatId] = false;
            delete userSockets[chatId];
            const reason = lastDisconnect?.error?.output?.statusCode;
            if (reason !== DisconnectReason.loggedOut) {
                // Auto reconnect silently
            } else {
                try { fs.rmSync(sessionDir, { recursive: true, force: true }); } catch (e) {}
            }
        }
    });

    userSockets[chatId] = waSock;
    return waSock;
}

bot.onText(/\/start/, (msg) => {
    const chatId = msg.chat.id;
    if (msg.from.id === ADMIN_ID || authenticatedUsers.has(chatId)) {
        authenticatedUsers.add(chatId);
        bot.sendMessage(chatId, "👋 **WhatsApp Checker Control Panel:**", {
            parse_mode: "Markdown",
            reply_markup: getMainButtons()
        });
    } else {
        userStates[chatId] = "WAITING_FOR_PASSWORD";
        bot.sendMessage(chatId, "🔒 **Password Required!** Doya kore password din:");
    }
});

bot.on('callback_query', async (query) => {
    const chatId = query.message.chat.id;
    const action = query.data;

    bot.answerCallbackQuery(query.id);

    if (!authenticatedUsers.has(chatId) && query.from.id !== ADMIN_ID) {
        return bot.sendMessage(chatId, "🔒 Password din.");
    }

    if (action === "cmd_qr_link") {
        connectionNotified[chatId] = false;
        bot.sendMessage(chatId, "⏳ QR Code generate kora hocche...");
        await getUserSocket(chatId, true);

    } else if (action === "cmd_link") {
        userStates[chatId] = "WAITING_FOR_LINK_NUMBER";
        bot.sendMessage(chatId, "📲 Apnar WhatsApp number din (Country code সহ, e.g. `8801700000000`):", { parse_mode: "Markdown" });

    } else if (action === "cmd_check") {
        const waSock = userSockets[chatId];
        // Dynamic Check: socket active thaklei allow korbe
        const isConnected = waSock && (waSock.user || waSock.authState?.creds?.me || waSock.authState?.creds?.registered);

        if (!isConnected) {
            return bot.sendMessage(chatId, "⚠️ Prothome WhatsApp link/scan korun!", { reply_markup: getMainButtons() });
        }
        userStates[chatId] = "WAITING_FOR_CHECK_NUMBER";
        bot.sendMessage(chatId, "🔍 Jey number check korben seti din (e.g. `8801800000000`):", { parse_mode: "Markdown" });

    } else if (action === "cmd_help") {
        const waSock = userSockets[chatId];
        const isConnected = waSock && (waSock.user || waSock.authState?.creds?.me || waSock.authState?.creds?.registered) ? "✅ Connected" : "❌ Not Connected";
        bot.sendMessage(chatId, `ℹ️ **Bot Status:** ${isConnected}`, { reply_markup: getMainButtons() });
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
            return bot.sendMessage(chatId, "🎉 Access Granted!", { reply_markup: getMainButtons() });
        } else {
            return bot.sendMessage(chatId, "❌ Bhul Password!");
        }
    }

    const state = userStates[chatId];

    if (state === "WAITING_FOR_LINK_NUMBER") {
        delete userStates[chatId];
        const phone = text.replace(/[^0-9]/g, '');

        bot.sendMessage(chatId, "⏳ Pairing code generate kora hocche...");

        try {
            const waSock = await getUserSocket(chatId);
            await delay(4000);

            let code = await waSock.requestPairingCode(phone);
            code = code?.match(/.{1,4}/g)?.join("-") || code;

            bot.sendMessage(chatId, `🔑 **Pairing Code:** \`${code}\`\n\n(Note: Code e somossa hole **Scan QR Code** option use korun)`, {
                parse_mode: "Markdown",
                reply_markup: getMainButtons()
            });
        } catch (err) {
            bot.sendMessage(chatId, "❌ Code fail hoyeche. **Scan QR Code** button try korun.", { reply_markup: getMainButtons() });
        }

    } else if (state === "WAITING_FOR_CHECK_NUMBER") {
        delete userStates[chatId];
        const waSock = userSockets[chatId];

        if (!waSock) {
            return bot.sendMessage(chatId, "⚠️ WhatsApp connect kora nei!", { reply_markup: getMainButtons() });
        }

        const checkPhone = text.replace(/[^0-9]/g, '');
        const jid = `${checkPhone}@s.whatsapp.net`;
        bot.sendMessage(chatId, `⏳ \`+${checkPhone}\` checking...`, { parse_mode: "Markdown" });

        try {
            const [result] = await waSock.onWhatsApp(checkPhone);

            if (!result || !result.exists) {
                bot.sendMessage(chatId, `📱 **Number:** \`+${checkPhone}\`\nSTATUS: ✅ **FRESH NUMBER**\nSend Success Chance: **95%**`, { parse_mode: "Markdown", reply_markup: getMainButtons() });
            } else {
                let profilePic = null, statusBio = null;
                try { profilePic = await waSock.profilePictureUrl(jid, 'image'); } catch (e) {}
                try { statusBio = await waSock.fetchStatus(jid); } catch (e) {}

                let statusText = (!profilePic && !statusBio) ? "⚠️ **SEMI-FRESH (75% Delivery Rate)**" : "❌ **LOGIN NOT AVAILABLE (Active Account)**";

                bot.sendMessage(chatId, `📱 **Number:** \`+${checkPhone}\`\nSTATUS: ${statusText}\nBio: \`${statusBio?.status || "None"}\``, { parse_mode: "Markdown", reply_markup: getMainButtons() });
            }
        } catch (error) {
            bot.sendMessage(chatId, "❌ Check failed.", { reply_markup: getMainButtons() });
        }
    }
});
    
