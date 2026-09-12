const { default: makeWASocket, useMultiFileAuthState, Browsers, DisconnectReason } = require('@whiskeysockets/baileys');
const { Bot, Keyboard } = require('grammy');
const fs = require('fs');

// ক্লাউডের এনভায়রনমেন্ট ভ্যারিয়েবল থেকে টোকেন নেবে, না পেলে সরাসরি কাজ করবে
const BOT_TOKEN = process.env.BOT_TOKEN || '8828385782:AAG1W02m2glBA4jI3jVFyBMk1-6Ly296HBk';
const bot = new Bot(BOT_TOKEN);

let waSocket = null;
let isConnected = false;
let userStates = {};

const replyMenu = new Keyboard()
    .text('🎁 Check Numbers').text('🔗 Link WhatsApp').row()
    .text('🎂 My Profile').text('📊 Status Info').row()
    .text('⚙️ Settings').text('🆘 Support')
    .resized();

async function startWhatsApp(chatId = null) {
    const { state, saveCreds } = await useMultiFileAuthState('auth_info_baileys');

    waSocket = makeWASocket({
        auth: state,
        printQRInTerminal: false,
        browser: Browsers.macOS('Chrome'),
        logger: require('pino')({ level: 'silent' })
    });

    waSocket.ev.on('creds.update', saveCreds);

    waSocket.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect } = update;
        if (connection === 'open') {
            isConnected = true;
            if (chatId) bot.api.sendMessage(chatId, '✅ <b>হোয়াটসঅ্যাপ সফলভাবে লিংক হয়েছে!</b>', { parse_mode: 'HTML' });
        } else if (connection === 'close') {
            isConnected = false;
            const shouldReconnect = (lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut);
            if (shouldReconnect) {
                setTimeout(() => startWhatsApp(), 3000);
            }
        }
    });
}

startWhatsApp();

bot.command('start', (ctx) => {
    ctx.reply('⚡ <b>REX WS CHECKER BOT</b> ⚡\nনম্বর চেক করতে নিচের মেনু ব্যবহার করুন।', {
        parse_mode: 'HTML',
        reply_markup: replyMenu
    });
});

bot.on('message:text', async (ctx) => {
    const text = ctx.message.text;
    const userId = ctx.from.id;
    const chatId = ctx.chat.id;

    if (text.startsWith('/')) return;

    if (text === '🔗 Link WhatsApp') {
        userStates[userId] = 'waiting_for_phone';
        return ctx.reply('📱 আপনার হোয়াটসঅ্যাপ নম্বরটি কান্ট্রি কোডসহ পাঠান (যেমন: <code>88017XXXXXXXXX</code>):', { parse_mode: 'HTML' });
    }

    if (userStates[userId] === 'waiting_for_phone') {
        delete userStates[userId];
        const phone = text.replace(/\D/g, '');
        await ctx.reply(`⏳ <code>+${phone}</code> নম্বরের জন্য পেয়ারিং কোড তৈরি হচ্ছে...`, { parse_mode: 'HTML' });
        
        await startWhatsApp(chatId);
        setTimeout(async () => {
            try {
                let code = await waSocket.requestPairingCode(phone);
                bot.api.sendMessage(chatId, `🔗 <b>পেয়ারিং কোড:</b> <code>${code}</code>\n\nহোয়াটসঅ্যাপে Linked Devices > Link with phone number instead-এ গিয়ে এই কোডটি দিন।`, { parse_mode: 'HTML' });
            } catch (e) {
                bot.api.sendMessage(chatId, '❌ কোড আনতে সমস্যা হয়েছে। আবার নম্বর দিয়ে চেষ্টা করুন।');
            }
        }, 4000);
        return;
    }

    const numbers = [...new Set((text.match(/\+?\d{10,15}/g) || []).map(n => n.replace(/\D/g, '')))];
    if (numbers.length === 0) return;

    if (!isConnected || !waSocket) {
        return ctx.reply('❌ প্রথমে <b>🔗 Link WhatsApp</b> এ ক্লিক করে অ্যাকাউন্ট লিংক করুন।', { parse_mode: 'HTML' });
    }

    const statusMsg = await ctx.reply(`⏳ চেক করা হচ্ছে... মোট নম্বর: ${numbers.length}`);
    let registered = [], no_account = [];

    for (let num of numbers) {
        try {
            const [res] = await waSocket.onWhatsApp(num + '@s.whatsapp.net');
            if (res && res.exists) {
                registered.push(`✅ <code>+${num}</code>`);
            } else {
                no_account.push(`⚠️ <code>+${num}</code>`);
            }
        } catch {
            no_account.push(`⚠️ <code>+${num}</code>`);
        }
    }

    let resText = `📊 <b>ফলাফল:</b>\n\n✅ Registered (${registered.length}):\n` + 
        (registered.slice(0, 20).join('\n') || 'None') + 
        `\n\n⚠️ No Account (${no_account.length}):\n` + 
        (no_account.slice(0, 20).join('\n') || 'None');

    await bot.api.editMessageText(chatId, statusMsg.message_id, resText, { parse_mode: 'HTML' });
});

bot.start();
