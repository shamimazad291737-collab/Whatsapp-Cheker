const { default: makeWASocket, useMultiFileAuthState, disconnectReason } = require('@whiskeysockets/baileys');
const TelegramBot = require('node-telegram-bot-api');
const express = require('express');
const fs = require('fs');

const TELEGRAM_TOKEN = '8828385782:AAHbRFf0YcFqmWSXiAH1mYXMpUxRdACRFhE';
const ADMIN_ID = 7388500439;

const app = express();
const PORT = process.env.PORT || 3000;
app.get('/', (req, res) => res.send('Bot is Running!'));
app.listen(PORT, () => console.log(`Server listening on port ${PORT}`));

const bot = new TelegramBot(TELEGRAM_TOKEN, { polling: true });
const userSockets = {}; 

async function getUserSocket(chatId) {
    if (userSockets[chatId]) return userSockets[chatId];

    const sessionDir = `./sessions/session_${chatId}`;
    const { state, saveCreds } = await useMultiFileAuthState(sessionDir);

    const waSock = makeWASocket({
        auth: state,
        printQRInTerminal: false
    });

    waSock.ev.on('creds.update', saveCreds);
    waSock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect } = update;
        if (connection === 'open') {
            bot.sendMessage(chatId, "✅ Apnar WhatsApp successfully connect hoye geche! Ebar jekono number pathiye check korun.");
        } else if (connection === 'close') {
            delete userSockets[chatId];
            const shouldReconnect = (lastDisconnect.error?.output?.statusCode !== disconnectReason.loggedOut);
            if (shouldReconnect) getUserSocket(chatId);
        }
    });

    userSockets[chatId] = waSock;
    return waSock;
}

bot.onText(/\/start/, (msg) => {
    bot.sendMessage(msg.chat.id, "👋 Swagotom!\n\nBot use korte apnar WhatsApp connect korun:\n👉 `/connect 8801XXXXXXXXX` (Apnar number din)\n\nCode pele WhatsApp > Linked Devices-e giye code-ti din.", { parse_mode: "Markdown" });
});

bot.onText(/\/connect (.+)/, async (msg, match) => {
    const chatId = msg.chat.id;
    const phone = match[1].trim().replace('+', '').replace(/ /g, '');

    if (isNaN(phone)) {
        return bot.sendMessage(chatId, "❌ Sothik number din. Example: `/connect 8801700000000`", { parse_mode: "Markdown" });
    }

    bot.sendMessage(chatId, "⏳ Apnar WhatsApp-er jonno Pairing Code generate hocche...");

    try {
        const waSock = await getUserSocket(chatId);
        
        setTimeout(async () => {
            try {
                let code = await waSock.requestPairingCode(phone);
                code = code?.match(/.{1,4}/g)?.join("-") || code;

                bot.sendMessage(chatId, `🔑 **Apnar Pairing Code:** \`${code}\`\n\n1. WhatsApp-e jan > Settings > Linked Devices\n2. **Link with phone number** select korun\n3. Ei code-ti bosan.`, { parse_mode: "Markdown" });
            } catch (err) {
                bot.sendMessage(chatId, "❌ Pairing Code toiri korte parini. Number thik ache kina dekhe abar try korun.");
            }
        }, 3000);

    } catch (e) {
        bot.sendMessage(chatId, "❌ Error: Connect kora jachhe na.");
    }
});

bot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    const text = msg.text?.trim();

    if (!text || text.startsWith('/')) return;

    const waSock = userSockets[chatId];
    if (!waSock || !waSock.authState.creds.registered) {
        return bot.sendMessage(chatId, "⚠️ Apnar WhatsApp connect kora nei!\n\nProthome `/connect 8801XXXXXXXXX` likhe apnar WhatsApp connect korun.", { parse_mode: "Markdown" });
    }

    const checkPhone = text.replace('+', '').replace(/ /g, '').replace(/-/g, '');
    if (isNaN(checkPhone)) return bot.sendMessage(chatId, "❌ Sothik number din.");

    bot.sendMessage(chatId, `⏳ ${checkPhone} check kora hocche...`);

    try {
        const [result] = await waSock.onWhatsApp(checkPhone);
        if (result && result.exists) {
            bot.sendMessage(chatId, `📱 Number: +${checkPhone}\n❌ **LOGIN NOT AVAILABLE** (Already active)`);
        } else {
            bot.sendMessage(chatId, `📱 Number: +${checkPhone}\n✅ **FRESH / HIGH OTP RATE** (Account nei, OTP ashbe)`);
        }
    } catch (error) {
        bot.sendMessage(chatId, "❌ Check korte shomossha hoyeche.");
    }
});
