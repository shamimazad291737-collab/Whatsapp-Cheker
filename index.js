const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require("@whiskeysockets/baileys");
const { Bot } = require("grammy");
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

// পেয়ারিং কোড দিয়ে হোয়াটসঅ্যাপ কানেক্ট করার ফাংশন
async function connectWhatsAppWithPairingCode(phoneNumber, ctx) {
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
            await ctx.reply("✅ <b>হোয়াটসঅ্যাপ সফলভাবে লিংক হয়েছে!</b> এখন আপনি নম্বর চেক করতে পারবেন।", { parse_mode: "HTML" });
        } else if (connection === "close") {
            isConnected = false;
            const shouldReconnect = lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
            if (shouldReconnect) {
                // রিকানেক্ট লজিক
            }
        }
    });

    if (!waSocket.authState.creds.registered) {
        setTimeout(async () => {
            try {
                let code = await waSocket.requestPairingCode(phoneNumber);
                
                // আপনার দেওয়া ফরম্যাট (RX-RX-RX-RX বা RXRXRXRX) অনুযায়ী সাজানো
                let customFormatCode = `RX${code?.match(/.{1,4}/g)?.join("RX") || code}RX`;

                await ctx.reply(
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
                await ctx.reply("❌ পেয়ারিং কোড আনতে সমস্যা হয়েছে। আবার চেষ্টা করুন।");
            }
        }, 3000);
    }
}

// টেলিগ্রাম কমান্ডস
bot.command("start", async (ctx) => {
    const welcomeMsg = `⚡ <b>REX WS CHECKER BOT</b> ⚡\n━━━━━━━━━━━━━━━━━━━━━━\n\nনম্বর লিংক করতে লিখুন: <code>/link আপনারনম্বর</code>\nউদাহরণ: <code>/link 88017XXXXXXXX</code>`;
    await ctx.reply(welcomeMsg, { parse_mode: "HTML" });
});

bot.command("link", async (ctx) => {
    const text = ctx.match;
    const phone = text.replace(/\D/g, "");
    
    if (phone.length < 10) {
        await ctx.reply("❌ সঠিক নম্বর দিন। উদাহরণ: <code>/link 88017XXXXXXXX</code>", { parse_mode: "HTML" });
        return;
    }

    await ctx.reply(`⏳ <code>+${phone}</code> নম্বরের জন্য পেয়ারিং কোড তৈরি করা হচ্ছে...`, { parse_mode: "HTML" });
    connectWhatsAppWithPairingCode(phone, ctx);
});

// নম্বর চেকিং হ্যান্ডলার
bot.on("message:text", async (ctx) => {
    const text = ctx.message.text;
    if (text.startsWith("/")) return;

    const rawNumbers = text.match(/\+?\d{10,15}/g) || [];
    const numbers = [...new Set(rawNumbers.map(n => n.replace(/\D/g, '')))];

    if (numbers.length === 0) return;

    if (!isConnected || !waSocket) {
        await ctx.reply("❌ প্রথমে আপনার হোয়াটসঅ্যাপ অ্যাকাউন্ট লিংক করুন! ব্যবহার করুন: <code>/link নম্বর</code>", { parse_mode: "HTML" });
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

    await ctx.api.editMessageText(ctx.chat.id, statusMsg.message_id, resultText, { parse_mode: "HTML" });
});

bot.start();