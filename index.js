const { default: makeWASocket, useMultiFileAuthState, Browsers, DisconnectReason } = require('@whiskeysockets/baileys');
const { Bot, Keyboard } = require('grammy');
const fs = require('fs');

const BOT_TOKEN = process.env.BOT_TOKEN || '8828385782:AAG1W02m2glBA4jI3jVFyBMk1-6Ly296HBk';
const bot = new Bot(BOT_TOKEN);

const ADMIN_ID = 123456789; // আপনার টেলিগ্রাম ইউজার আইডি এখানে বসাবেন

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
            if (chatId) {
                bot.api.sendMessage(chatId, '✅ <b>হোয়াটসঅ্যাপ সফলভাবে এবং স্থায়ীভাবে লিংক হয়েছে!</b>', { parse_mode: 'HTML' });
            }
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
    // যেকোনো সময় /start দিলে ইউজারের আগের আটকে থাকা স্টেট ক্লিয়ার হয়ে যাবে
    delete userStates[ctx.from.id];
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
        delete userStates[userId];
        if (isConnected) {
            return ctx.reply('✅ আপনার হোয়াটসঅ্যাপ অ্যাকাউন্ট ইতিমধ্যে সফলভাবে লিংক করা আছে!', { parse_mode: 'HTML' });
        }
        userStates[userId] = 'waiting_for_phone';
        return ctx.reply('📱 আপনার হোয়াটসঅ্যাপ নম্বরটি কান্ট্রি কোডসহ পাঠান (যেমন: <code>88017XXXXXXXXX</code>):', { parse_mode: 'HTML' });
    }

    if (text === '🎁 Check Numbers') {
        delete userStates[userId];
        if (!isConnected) {
            return ctx.reply('❌ প্রথমে <b>🔗 Link WhatsApp</b> এ ক্লিক করে অ্যাকাউন্ট লিংক করুন।', { parse_mode: 'HTML' });
        }
        userStates[userId] = 'waiting_for_numbers';
        const limitText = (userId === ADMIN_ID) ? '<b>(আপনি অ্যাডমিন, তাই আনলিমিটেড নম্বর চেক করতে পারবেন)</b>' : '<b>(সর্বোচ্চ ১০টি নম্বর একবারে দেওয়া যাবে)</b>';
        return ctx.reply(`📥 যে নম্বরগুলো চেক করতে চান সেগুলো সেন্ড করুন ${limitText}:`, { parse_mode: 'HTML' });
    }

    // যদি ইউজার অন্য কোনো মেনু বা বাটন চাপেন, তবে স্টেট ক্লিয়ার করে মেনু দেখাবে
    if (['🎂 My Profile', '📊 Status Info', '⚙️ Settings', '🆘 Support'].includes(text)) {
        delete userStates[userId];
        return ctx.reply(`ℹ️ আপনি <b>${text}</b> অপশনটি বেছে নিয়েছেন। (এই ফিচারটি শীঘ্রই আপডেট করা হবে)`, { 
            parse_mode: 'HTML',
            reply_markup: replyMenu 
        });
    }

    if (userStates[userId] === 'waiting_for_phone') {
        delete userStates[userId];
        const phone = text.replace(/\D/g, '');
        if (!phone) {
            return ctx.reply('⚠️ সঠিক ফরম্যাটে নম্বর দিন। আবার <b>🔗 Link WhatsApp</b>-এ ক্লিক করুন।', { parse_mode: 'HTML' });
        }
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

    // নম্বর প্রসেসিং লজিক (শুধুমাত্র যখন ইউজার 'waiting_for_numbers' স্টেটে থাকবে অথবা সরাসরি লিস্ট পাঠাবে)
    const numbers = [...new Set((text.match(/\+?\d{10,15}/g) || []).map(n => n.replace(/\D/g, '')))];
    
    if (numbers.length === 0) {
        return ctx.reply('⚠️ কোনো সঠিক নম্বর পাওয়া যায়নি। দয়া করে সঠিক ফরম্যাটে নম্বর দিন অথবা মেনু ব্যবহার করুন।', { parse_mode: 'HTML' });
    }

    if (userId !== ADMIN_ID && numbers.length > 10) {
        delete userStates[userId];
        return ctx.reply(`⚠️ <b>সীমাবদ্ধতা লঙ্ঘন!</b> সাধারণ ব্যবহারকারী হিসেবে আপনি একসাথে ${numbers.length}টি নম্বর দিয়েছেন। একবারে সর্বোচ্চ <b>১০টি</b> নম্বর চেক করা যাবে।`, { parse_mode: 'HTML' });
    }

    if (userStates[userId] === 'waiting_for_numbers') {
        delete userStates[userId];
    }

    if (!isConnected || !waSocket) {
        return ctx.reply('❌ প্রথমে <b>🔗 Link WhatsApp</b> এ ক্লিক করে অ্যাকাউন্ট লিংক করুন।', { parse_mode: 'HTML' });
    }

    const statusMsg = await ctx.reply(`⏳ নিখুঁতভাবে চেক করা হচ্ছে... মোট নম্বর: ${numbers.length}`);
    let registered = [], no_account = [];

    for (let num of numbers) {
        try {
            const results = await waSocket.onWhatsApp(num + '@s.whatsapp.net');
            if (results && results.length > 0 && results[0].exists) {
                registered.push(`✅ <code>+${num}</code>`);
            } else {
                no_account.push(`⚠️ <code>+${num}</code>`);
            }
        } catch (e) {
            no_account.push(`⚠️ <code>+${num}</code>`);
        }
        await new Promise(resolve => setTimeout(resolve, 300));
    }

    let resText = `📊 <b>নিখুঁত ফলাফল:</b>\n\n✅ Registered (${registered.length}):\n` + 
        (registered.join('\n') || 'None') + 
        `\n\n⚠️ No Account (${no_account.length}):\n` + 
        (no_account.join('\n') || 'None');

    await bot.api.editMessageText(chatId, statusMsg.message_id, resText, { parse_mode: 'HTML' });
});

bot.start();
