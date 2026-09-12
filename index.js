const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require("@whiskeysockets/baileys");
const { Bot, InlineKeyboard } = require("grammy");
const pino = require("pino");
const http = require("http");

// রেন্ডার সার্ভার সচল রাখার জন্য HTTP সার্ভার
const server = http.createServer((req, res) => {
    res.writeHead(200, { "Content-Type": "text/plain" });
    res.end("REX WS CHECKER Bot Active");
});
const PORT = process.env.PORT || 8080;
server.listen(PORT, () => console.log(`HTTP Server running on port ${PORT}`));

const BOT_TOKEN = process.env.BOT_TOKEN || "YOUR_BOT_TOKEN_HERE";
const bot = new Bot(BOT_TOKEN);

let waSocket = null;
let isConnected = false;

// ইউজারদের সাময়িকভাবে ফোন নম্বর ইনপুট নেওয়ার স্টেট ট্র্যাক করার জন্য
let userStates = {};

// প্রিমিয়াম ইনলাইন কিবোর্ড ডিজাইন
const inlineMenu = new InlineKeyboard()
    .text("🎁 Check Numbers", "btn_check")
    .text("🔗 Link WhatsApp", "btn_link").row()
    .text("👛 My Profile", "btn_profile")
    .text("📊 Status Info", "btn_status").row()
    .text("🆘 Support", "btn_support");

// পেয়ারিং কোড দিয়ে হোয়াটসঅ্যাপ কানেক্ট করার ফাংশন
async function connectWhatsAppWithPairingCode(phoneNumber, ctx, chatId) {
    const { state, saveCreds } = await useMultiFileAuthState("auth_info_baileys");
    
    waSocket = makeWASocket({
        auth: state,
        printQRInTerminal: false,
        logger: pino({ level: "silent" })
    });

    waSocket.ev.on("creds.update", saveCreds);

    waSocket.ev.on("connection.update", async (update) => {
        const { connection, lastDisconnect } = update;
        if (connection === "open") {
            isConnected = true;
            console.log("WhatsApp Connected Successfully!");
            await bot.api.sendMessage(chatId, "✅ <b>হোয়াটসঅ্যাপ সফলভাবে লিংক হয়েছে!</b> এখন আপনি নম্বর চেক করতে পারবেন।", { parse_mode: "HTML" });
        } else if (connection === "close") {
            isConnected = false;
        }
    });

    if (!waSocket.authState.creds.registered) {
        setTimeout(async () => {
            try {
                let code = await waSocket.requestPairingCode(phoneNumber);
                let customFormatCode = `RX${code?.match(/.{1,4}/g)?.join("RX") || code}RX`;

                await bot.api.sendMessage(
                    chatId,
                    `🔗 <b>আপনার হোয়াটসঅ্যাপ পেয়ারিং কোড:</b>\n\n` +
                    `<code>${customFormatCode}</code>\n\n` +
                    `<b>কীভাবে কানেক্ট করবেন:</b>\n` +
                    `১. আপনার হোয়াটসঅ্যাপ অ্যাপে যান।\n` +
                    `২. Settings > Linked Devices > Link a Device-এ যান।\n` +
                    `৩. নিচে থাকা <b>'Link with phone number instead'</b> এ ক্লিক করুন এবং এই কোডটি দিন।`,
                    { parse_mode: "HTML" }
                );
            } catch (e) {
                console.log("Pairing Error:", e);
                await bot.api.sendMessage(chatId, "❌ পেয়ারিং কোড আনতে সমস্যা হয়েছে। আবার চেষ্টা করুন।");
            }
        }, 3000);
    }
}

// /start কমান্ড এবং ইনলাইন মেনু
bot.command("start", async (ctx) => {
    const welcomeMsg = `⚡ <b>REX WS CHECKER BOT</b> ⚡\n━━━━━━━━━━━━━━━━━━━━━━\n\nনম্বর চেক করতে নিচের মেনু থেকে অপশন বেছে নিন বা নম্বর পাঠান।`;
    await ctx.reply(welcomeMsg, { parse_mode: "HTML", reply_markup: inlineMenu });
});

// ইনলাইন বাটন ক্লিক হ্যান্ডলার (Callback Query)
bot.callbackQuery("btn_check", async (ctx) => {
    await ctx.answerCallbackQuery();
    await ctx.reply("📥 চেকের জন্য নম্বরগুলোর লিস্ট বা মেসেজ পাঠান।", { parse_mode: "HTML" });
});

bot.callbackQuery("btn_link", async (ctx) => {
    await ctx.answerCallbackQuery();
    userStates[ctx.from.id] = "waiting_for_phone";
    await ctx.reply("📱 আপনার হোয়াটসঅ্যাপ নম্বরটি কান্ট্রি কোডসহ পাঠান (যেমন: <code>88017XXXXXXXXX</code>):", { parse_mode: "HTML" });
});

bot.callbackQuery("btn_profile", async (ctx) => {
    await ctx.answerCallbackQuery();
    const linkStatus = isConnected ? "✅ Connected" : "❌ Not Connected";
    await ctx.reply(`👤 <b>ইউজার প্রোফাইল:</b>\n\nহোয়াটসঅ্যাপ স্ট্যাটাস: ${linkStatus}`, { parse_mode: "HTML" });
});

bot.callbackQuery("btn_status", async (ctx) => {
    await ctx.answerCallbackQuery();
    const infoText = `📊 <b>স্ট্যাটাস নির্দেশিকা:</b>\n\n✅ <b>Registered:</b> হোয়াটসঅ্যাপ চালু আছে\n⚠️ <b>No Account:</b> অ্যাকাউন্ট নেই`;
    await ctx.reply(infoText, { parse_mode: "HTML" });
});

bot.callbackQuery("btn_support", async (ctx) => {
    await ctx.answerCallbackQuery();
    await ctx.reply("💬 এডমিন সাপোর্ট: @XSAIM_X9", { parse_mode: "HTML" });
});

// টেক্সট মেসেজ ও নম্বর চেকিং হ্যান্ডলার
bot.on("message:text", async (ctx) => {
    const text = ctx.message.text;
    const userId = ctx.from.id;
    const chatId = ctx.chat.id;

    if (text.startsWith("/")) return;

    // যদি ইউজার লিংকের জন্য নম্বর পাঠিয়ে থাকে
    if (userStates[userId] === "waiting_for_phone") {
        const phone = text.replace(/\D/g, "");
        if (phone.length < 10) {
            await ctx.reply("❌ সঠিক নম্বর দিন। আবার চেষ্টা করুন।");
            return;
        }
        delete userStates[userId];
        await ctx.reply(`⏳ <code>+${phone}</code> নম্বরের জন্য পেয়ারিং কোড তৈরি করা হচ্ছে...`, { parse_mode: "HTML" });
        connectWhatsAppWithPairingCode(phone, ctx, chatId);
        return;
    }

    const rawNumbers = text.match(/\+?\d{10,15}/g) || [];
    const numbers = [...new Set(rawNumbers.map(n => n.replace(/\D/g, '')))];

    if (numbers.length === 0) return;

    if (!isConnected || !waSocket) {
        await ctx.reply("❌ প্রথমে আপনার হোয়াটসঅ্যাপ অ্যাকাউন্ট লিংক করুন! নিচের মেনু থেকে <b>Link WhatsApp</b> এ ক্লিক করুন।", { parse_mode: "HTML", reply_markup: inlineMenu });
        return;
    }

    const statusMsg = await ctx.reply(`⏳ <b>প্রসেসিং চলছে...</b>\nমোট নম্বর: <code>${numbers.length}</code> টি`, { parse_mode: "HTML" });

    let registered = [];
    let no_account = [];

    for (let num of numbers) {
        try {
            const jid = `${num}@s.whatsapp.net`;
            const [result] = await waSocket.onWhatsApp(jid);
            
            if (result && result.exists) {
                registered.push(`✅ <code>+${num}</code>`);
            } else {
                no_account.push(`⚠️ <code>+${num}</code>`);
            }
        } catch (e) {
            no_account.push(`⚠️ <code>+${num}</code>`);
        }
    }

    let resultText = `📊 <b>চেক ফলাফল (Total: ${numbers.length}):</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n`;
    resultText += `✅ <b>Registered (${registered.length}):</b>\n` + (registered.slice(0, 30).join("\n") || "None");
    resultText += `\n\n⚠️ <b>No Account (${no_account.length}):</b>\n` + (no_account.slice(0, 20).join("\n") || "None");

    await ctx.api.editMessageText(chatId, statusMsg.message_id, resultText, { parse_mode: "HTML" });
});

bot.start();
