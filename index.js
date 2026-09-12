const TelegramBot = require('node-telegram-bot-api');
const axios = require('axios');
const fs = require('fs');

const TOKEN = process.env.BOT_TOKEN;
if (!TOKEN) {
    console.error("Error: BOT_TOKEN is missing in environment variables!");
    process.exit(1);
}

const bot = new TelegramBot(TOKEN, { polling: true });
const DB_FILE = 'database.json';

function loadDatabase() {
    if (!fs.existsSync(DB_FILE)) return {};
    try {
        return JSON.parse(fs.readFileSync(DB_FILE, 'utf8'));
    } catch (e) {
        return {};
    }
}

function saveDatabase(data) {
    fs.writeFileSync(DB_FILE, JSON.stringify(data, null, 2));
}

bot.onText(/\/start/, (msg) => {
    const chatId = msg.chat.id;
    const welcomeText = `স্বাগতম! আপনার USA নম্বর এবং ওটিপি লিংক ম্যানেজ করার বট এটি।\n\n` +
        `📌 **নম্বর যোগ করতে নিচের মতো করে একসাথে পেস্ট করুন:**\n` +
        `\`/addmany\`\n` +
        `+19793930893 http://169.58.215.134:11111/sms/wa-...\n` +
        `+16316936639 http://169.58.215.134:11111/sms/wa-...\n\n` +
        `সব নম্বর ও বাটন দেখতে নিচের মেনু থেকে **📋 সব নম্বর (OTP Check)** এ ক্লিক করুন।`;
    
    const replyKeyboard = {
        reply_markup: {
            keyboard: [
                [{ text: "📋 সব নম্বর (OTP Check)" }, { text: "❌ সব নম্বর মুছুন" }]
            ],
            resize_keyboard: true
        }
    };

    bot.sendMessage(chatId, welcomeText, { parse_mode: 'Markdown', ...replyKeyboard });
});

bot.onText(/\/addmany([\s\S]*)/, (msg, match) => {
    const chatId = msg.chat.id.toString();
    const rawText = match[1];
    
    if (!rawText || !rawText.trim()) {
        bot.sendMessage(chatId, "⚠️ সঠিক ফরম্যাটে নম্বর ও লিংক দিন।");
        return;
    }

    const lines = rawText.trim().split('\n');
    let count = 0;
    
    let db = loadDatabase();
    if (!db[chatId]) db[chatId] = [];

    lines.forEach(line => {
        line = line.trim();
        if (!line) return;

        const parts = line.split(/\s+/);
        if (parts.length >= 2) {
            const number = parts[0];
            const apiUrl = parts.slice(1).join(' ');
            
            db[chatId].push({
                number: number,
                api_url: apiUrl
            });
            count++;
        }
    });

    saveDatabase(db);

    if (count > 0) {
        bot.sendMessage(chatId, `✅ সফলভাবে **${count}টি** নম্বর সেভ করা হয়েছে!\nনিচের মেনু থেকে বাটন দেখতে **📋 সব নম্বর (OTP Check)** এ ক্লিক করুন।`, { parse_mode: 'Markdown' });
    } else {
        bot.sendMessage(chatId, "⚠️ কোনো নম্বর বা লিংক খুঁজে পাওয়া যায়নি।");
    }
});

bot.on('message', async (msg) => {
    const chatId = msg.chat.id.toString();
    const text = msg.text;

    if (!text) return;

    if (text === "📋 সব নম্বর (OTP Check)" || text === "/numbers") {
        const db = loadDatabase();

        if (!db[chatId] || db[chatId].length === 0) {
            bot.sendMessage(chatId, "❌ আপনার কোনো নম্বর সেভ করা নেই। `/addmany` লিখে নম্বর যোগ করুন।");
            return;
        }

        const inlineKeyboard = [];
        db[chatId].forEach((item, index) => {
            inlineKeyboard.push([{
                text: `🇺🇸 ${item.number} (OTP চেক করুন)`,
                callback_data: `check_${chatId}_${index}`
            }]);
        });

        bot.sendMessage(chatId, "আপনার সেভ করা নম্বরগুলোর লিস্ট নিচে দেওয়া হলো। যেকোনো নম্বরের ওটিপি দেখতে তার পাশের বাটনে ক্লিক করুন:", {
            reply_markup: {
                inline_keyboard: inlineKeyboard
            }
        });
    }

    if (text === "❌ সব নম্বর মুছুন") {
        let db = loadDatabase();
        if (db[chatId]) {
            db[chatId] = [];
            saveDatabase(db);
            bot.sendMessage(chatId, "🗑️ আপনার সেভ করা সব নম্বর মুছে ফেলা হয়েছে।");
        } else {
            bot.sendMessage(chatId, "⚠️ আপনার কোনো নম্বর সেভ করা ছিল না।");
        }
    }
});

bot.on('callback_query', async (query) => {
    const chatId = query.message.chat.id.toString();
    const data = query.data;

    if (data.startsWith('check_')) {
        const parts = data.split('_');
        const targetChatId = parts[1];
        const index = parseInt(parts[2]);

        const db = loadDatabase();
        if (!db[targetChatId] || !db[targetChatId][index]) {
            bot.answerCallbackQuery(query.id, { text: "নম্বরের তথ্য পাওয়া যায়নি!" });
            return;
        }

        const item = db[targetChatId][index];
        bot.answerCallbackQuery(query.id, { text: `Checking ${item.number}...` });

        try {
            const response = await axios.get(item.api_url, { timeout: 10000 });
            const code = typeof response.data === 'string' ? response.data.trim() : JSON.stringify(response.data).trim();

            if (/^\d{3,10}$/.test(code)) {
                bot.sendMessage(chatId, `🎉 **OTP Received!**\nনম্বর: \`${item.number}\`\nকোড: \`${code}\``, { parse_mode: 'Markdown' });
            } else {
                bot.sendMessage(chatId, `⏳ **${item.number}** নম্বরে এখনও কোনো ওটিপি আসেনি!\n(Status: ${code || 'Empty'})`, { parse_mode: 'Markdown' });
            }
        } catch (error) {
            bot.sendMessage(chatId, `❌ **${item.number}** এর লিংক থেকে ডাটা ফেচ করতে সমস্যা হচ্ছে।`, { parse_mode: 'Markdown' });
        }
    }
});

console.log("Bot with Main Reply Keyboard is running successfully...");
