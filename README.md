# সহজ Telegram Music Bot (ফ্ল্যাট স্ট্রাকচার)

সব ফাইল একই ফোল্ডারে আছে — কোনো সাবফোল্ডার নেই, তাই GitHub অ্যাপ থেকে
একটি একটি করে আপলোড করা সহজ।

## ফাইল
- config.py — env ভেরিয়েবল
- clients.py — bot, assistant, pytgcalls, mongo সেটআপ
- db.py — Mongo-তে users/chats ট্র্যাক করে (broadcast-এর জন্য)
- helpers.py — smallcaps টেক্সট + র্যান্ডম processing টেক্সট/ইমোজি
- music_queue.py — প্রতি-চ্যাট কিউ এবং now-playing স্টেট
- nowplaying.py — থাম্বনেইল থেকে "Now Playing" কার্ড ইমেজ বানায়
- youtube.py — YouTube সার্চ + স্ট্রিম URL (ShrutiAPI)
- play.py — সব কমান্ড ও বাটন (/start, /play, /skip, /pause, /resume, /stop, /id, /broadcast)
- app.py — সবকিছু চালু করে (এটাই রান করতে হবে), keep-alive পিংও এখানেই আছে
- generate_session.py — assistant-এর STRING_SESSION বানানোর জন্য
- requirements.txt, Dockerfile, sample.env

## সেটআপ

1. **ক্রেডেনশিয়াল নাও**: API_ID/API_HASH (my.telegram.org), BOT_TOKEN (@BotFather),
   MONGO_DB_URI (mongodb.com ফ্রি ক্লাস্টার), LOG_GROUP_ID এবং OWNER_ID (@userinfobot)

2. **STRING_SESSION বানাও**: `python3 generate_session.py` চালাও (আলাদা অ্যাকাউন্ট ব্যবহার করো)

3. **SUPPORT_URL / CHANNEL_URL**: তোমার সাপোর্ট গ্রুপ ও আপডেট চ্যানেলের লিংক
   sample.env-এ দিয়ে দাও — এগুলো /start মেসেজের বাটনে ব্যবহার হয়।

4. **GitHub-এ আপলোড**: এই ফোল্ডারের সব ফাইল তোমার রিপোতে দিয়ে দাও (সব root-এ, কোনো ফোল্ডার বানাতে হবে না)

5. **Render-এ ডিপ্লয়**: New + > Web Service > Docker > Environment ট্যাবে
   sample.env-এর সব ভেরিয়েবল ভরো > Deploy।
   `RENDER_EXTERNAL_URL` খালি রেখে দাও — Render নিজেই সেট করে দেয়, বট
   এই URL-কেই প্রতি `PING_INTERVAL` সেকেন্ডে পিং করে ঘুমিয়ে পড়া থেকে বাঁচে।

6. **গ্রুপ সেটআপ**: Bot এবং Assistant দুটোকেই গ্রুপে যোগ করো, VC চালু করো, `/play <song>` চেষ্টা করো

## কমান্ড
- `/play <song>` — গান বাজাও বা কিউতে দাও (যদি আগে থেকেই কিছু বাজছে)
- `/skip` — পরের গান
- `/pause` / `/resume`
- `/stop` — VC থেকে বেরিয়ে যাও, কিউ ক্লিয়ার
- `/id` — নিজের এবং গ্রুপের আইডি
- `/reload` (শুধু গ্রুপ অ্যাডমিন/মালিক) — চেক করে বট অ্যাডমিন কি না
- `/broadcast <msg>` (শুধু OWNER_ID) — সব ইউজারকে মেসেজ পাঠাও
- `/addvd` (শুধু OWNER_ID) — পরের image/video/gif যা পাঠাবে, সেটাই এখন থেকে `/start` মেসেজের সাথে সবাইকে যাবে
- `/delvd` (শুধু OWNER_ID) — `/start` মেসেজ থেকে সেট করা মিডিয়া সরিয়ে ফেলে

## নোট
`/skip` `/pause` `/resume` `/stop` শুধু গ্রুপ অ্যাডমিন বা OWNER_ID ব্যবহার করতে পারেন — সাধারণ ইউজার শুধু `/play` ব্যবহার করতে পারে।

## "Peer id invalid" এরর ফিক্স
এই এরর তখন আসত যখন assistant অ্যাকাউন্টের pyrogram সেশনে সেই
গ্রুপের peer/access_hash ক্যাশে থাকে না (কারণ assistant শুধু VC জয়েন
করে, সাধারণ মেসেজ পড়ে না)। এখন `app.py` স্টার্টআপে একবার
`assistant.get_dialogs()` চালিয়ে সব গ্রুপ/চ্যানেলের peer ক্যাশে
নিয়ে নেয়, আর যদি তবুও কখনো এই এরর আসে তাহলে play.py স্বয়ংক্রিয়ভাবে
ডায়ালগ রিফ্রেশ করে একবার রিট্রাই করে।