import logging
import time
from pyrogram import Client
from pytgcalls import PyTgCalls
from motor.motor_asyncio import AsyncIOMotorClient

import config

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] - [%(levelname)s] - %(name)s - %(message)s",
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("pytgcalls").setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Compatibility shim: py-tgcalls==0.9.7 (খুব পুরনো)-এর raw-update handler
# ধরে নেয় যে UpdateGroupCall অবজেক্টের সরাসরি `.chat_id` অ্যাট্রিবিউট
# আছে (data2[update.chat_id])। নতুন kurigram/pyrogram স্কিমায় এই
# ফিল্ড সরিয়ে দেওয়া হয়েছে — এখন শুধু `.peer` (PeerChat/PeerChannel)
# পাওয়া যায়। এই কারণেই এই এররটি আসত:
#   AttributeError: 'UpdateGroupCall' object has no attribute 'chat_id'
# এই প্যাচ `.chat_id`-কে একটি computed property বানিয়ে দেয় যা `.peer`
# থেকে বের করে ঠিক সেই পুরনো আচরণ দিয়ে দেয় — py-tgcalls বা kurigram-এর
# ভার্সন না বদলে।
# ---------------------------------------------------------------------------
try:
    from pyrogram.raw.types import UpdateGroupCall, PeerChat, PeerChannel

    if "chat_id" not in UpdateGroupCall.__dict__:
        def _shim_chat_id(self):
            peer = getattr(self, "peer", None)
            if isinstance(peer, PeerChat):
                return peer.chat_id
            if isinstance(peer, PeerChannel):
                return peer.channel_id
            raise AttributeError("chat_id")

        UpdateGroupCall.chat_id = property(_shim_chat_id)
        logging.getLogger("MusicBot").info(
            "✅ UpdateGroupCall.chat_id compatibility shim প্রয়োগ হয়েছে"
        )
except Exception as _shim_err:  # প্যাচ কখনো ব্যর্থ হলেও বট ক্র্যাশ না করুক
    logging.getLogger("MusicBot").warning(
        f"⚠️ UpdateGroupCall compatibility shim বাদ দেওয়া হয়েছে: {_shim_err}"
    )

LOGGER = logging.getLogger("MusicBot")

# প্রসেস শুরুর সময় — গ্রুপ start মেসেজে uptime দেখানোর জন্য
START_TIME = time.monotonic()

bot = Client(
    name="MusicBot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    in_memory=True,
)

assistant = Client(
    name="Assistant",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    session_string=config.STRING_SESSION,
    in_memory=True,
)

call_py = PyTgCalls(assistant)

mongo_client = AsyncIOMotorClient(config.MONGO_DB_URI)
db = mongo_client["MusicBotDB"]