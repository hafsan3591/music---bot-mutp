import os

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
STRING_SESSION = os.getenv("STRING_SESSION", "")
LOG_GROUP_ID = int(os.getenv("LOG_GROUP_ID", "0"))
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
MONGO_DB_URI = os.getenv("MONGO_DB_URI", "")
PORT = int(os.getenv("PORT", "10000"))

# Start মেসেজের বাটনগুলোর লিংক (সাপোর্ট গ্রুপ / আপডেট চ্যানেল / মালিক)
SUPPORT_URL = os.getenv("SUPPORT_URL", "https://t.me/")
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/")
OWNER_URL = os.getenv("OWNER_URL", "https://t.me/hafsan_hun")

# Render নিজেই এই env variable দেয় (যেমন https://your-app.onrender.com)
# এটি দিয়ে বট নিজেকে পর্যায়ক্রমে পিং করে ঘুমিয়ে পড়া থেকে বাঁচায়।
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "")
PING_INTERVAL = int(os.getenv("PING_INTERVAL", "600"))  # সেকেন্ড (ডিফল্ট ১০ মিনিট)

# Assistant (userbot)-এর ইউজারনেম — /play চললে বট চেক করে যে
# এই অ্যাকাউন্ট গ্রুপে আছে কি না, আর না থাকলে এই ইউজারনেম দিয়ে
# (বা ইনভাইট লিংক দিয়ে) জয়েন করানোর চেষ্টা করে।
ASSISTANT_USERNAME = os.getenv("ASSISTANT_USERNAME", "Mitsuriass")