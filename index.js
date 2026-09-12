const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require("@whiskeysockets/baileys");
const { Bot, Keyboard } = require("grammy");
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
let userStates = {};

// নিচের রিপ্লাই কিবোর্ড লেআউট
const replyMenu = new Keyboard()
    .text("🎁 Check Numbers").text("🔗 Link WhatsApp").row()
    .text("🎂 My Profile").text("📊 Status Info").row()
    .text("⚙️ Settings").text("🆘 Support")
    .resized();

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
        const { connection } = update;
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

                await bot.api.sendMessage(
                    chatId,
                    `🔗 <b>আপনার হোয়াটসঅ্যাপ পেয়ারিং কোড:</b>\n\n` +
                    `<code>${code}</code>\n\n` +
                    `<b>কীভাবে কানেক্ট করবেন:</b>\n` +
                    `১. আপনার হোয়াটসঅ্যাপ অ্যাপে যান।\n` +
                    `২. Settings > Linked Devices > Link a Device-এ যান।\n` +
                    `৩. নিচে থাকা <b>'Link with phone number instead'</b> এ ক্লিক করুন এবং এই ৮ ডিজিটের কোডটি দিন।`,
                    { parse_mode: "HTML" }
                );
            } catch (e) {
                console.log("Pairing Error:", e);
                await bot.api.sendMessage(chatId, "❌ পেয়ারিং কোড আনতে সমস্যা হয়েছে। আবার চেষ্টা করুন।");
            }
        }, 3000);
    }
}

// /start কমান্ড এবং রিপ্লাই কিবোর্ড পাঠানো
bot.command("start", async (ctx) => {
    const welcomeMsg = `⚡ <b>REX WS CHECKER BOT</b> ⚡\n━━━━━━━━━━━━━━━━━━━━━━\n\nনম্বর চেক করতে নিচের মেনু থেকে অপশন বেছে নিন।`;
    await ctx.reply(welcomeMsg, { parse_mode: "HTML", reply_markup: replyMenu });
});

// টেক্সট মেসেজ ও মেনু বাটন হ্যান্ডলার
bot.on("message:text", async (ctx) => {
    const text = ctx.message.text;
    const userId = ctx.from.id;
    const chatId = ctx.chat.id;

    if (text.startsWith("/")) return;

    // মেনু বাটনের রেসপন্স
    if (text === "🎁 Check Numbers") {
        await ctx.reply("📥 চেকের জন্য নম্বরগুলোর লিস্ট বা মেসেজ পাঠান।", { parse_mode: "HTML" });
        return;
    }
    if (text === "🔗 Link WhatsApp") {
        userStates[userId] = "waiting_for_phone";
        await ctx.reply("📱 আপনার হোয়াটসঅ্যাপ নম্বরটি কান্ট্রি কোডসহ পাঠান (যেমন: <code>88017XXXXXXXXX</code>):", { parse_mode: "HTML" });
        return;
    }
    if (text === "🎂 My Profile") {
        const linkStatus = isConnected ? "✅ Connected" : "❌ Not Connected";
        await ctx.reply(`👤 <b>ইউজার প্রোফাইল:</b>\n\nহোয়াটসঅ্যাপ স্ট্যাটাস: ${linkStatus}`, { parse_mode: "HTML" });
        return;
    }
    if (text === "📊 Status Info") {
        const infoText = `📊 <b>স্ট্যাটাস নির্দেশিকা:</b>\n\n✅ <b>Registered:</b> হোয়াটসঅ্যাপ চালু আছে\n⚠️ <b>No Account:</b> অ্যাকাউন্ট নেই`;
        await ctx.reply(infoText, { parse_mode: "HTML" });
        return;
    }
    if (text === "⚙️ Settings") {
        await ctx.reply("⚙️ <b>সেটিংস:</b>\n\nনম্বর লিংক করতে নিচের <b>🔗 Link WhatsApp</b> বাটন ব্যবহার করুন।", { parse_mode: "HTML" });
        return;
    }
    if (text === "🆘 Support") {
        await ctx.reply("💬 এডমিন সাপোর্ট: @XSAIM_X9", { parse_mode: "HTML" });
        return;
    }

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
        await ctx.reply("❌ প্রথমে আপনার হোয়াটসঅ্যাপ অ্যাকাউন্ট লিংক করুন! নিচের <b>🔗 Link WhatsApp</b> বাটনে ক্লিক করুন।", { parse_mode: "HTML" });
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

bot.command("link", async (ctx) => {
    const text = ctx.match;
    const phone = text.replace(/\D/g, "");
    
    if (phone.length < 10) {
        await ctx.reply("❌ সঠিক নম্বর দিন। উদাহরণ: <code>/link 88017XXXXXXXX</code>", { parse_mode: "HTML" });
        return;
    }

    await ctx.reply(`⏳ <code>+${phone}</code> নম্বরের জন্য পেয়ারিং কোড তৈরি করা হচ্ছে...`, { parse_mode: "HTML" });
    connectWhatsAppWithPairingCode(phone, ctx, ctx.chat.id);
});

bot.start();
    
