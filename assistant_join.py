"""
প্রতিটি গ্রুপে মিউজিক বাজানোর আগে assistant (userbot) অ্যাকাউন্টের
সেখানে থাকা জরুরি — VC জয়েন করে সে-ই, বট নয়।

এই মডিউল চেক করে assistant ইতিমধ্যে গ্রুপে আছে কি না, আর
না থাকলে নিজে থেকেই জয়েন করানোর চেষ্টা করে:

  ১. গ্রুপ পাবলিক হলে (ইউজারনেম আছে) -> assistant সরাসরি সেই
     ইউজারনেম দিয়ে জয়েন করে নেয়।
  ২. গ্রুপ প্রাইভেট হলে -> বট (যে ইতিমধ্যে গ্রুপে আছে) একটি ইনভাইট
     লিংক বের করে, আর assistant সেটি দিয়ে জয়েন করে।
  ৩. শেষ উপায় -> বট নিজেই assistant-কে মেম্বার হিসেবে যোগ করার
     চেষ্টা করে (এর জন্য বটের "invite users" অ্যাডমিন অধিকার দরকার)।

তিনটিই ব্যর্থ হলে (যেমন বট নিজেই অ্যাডমিন নয়, বা assistant-এর প্রাইভেসি
সেটিং বাধা দিচ্ছে) caller-কে জানানো হয় যে ম্যানুয়ালি
@ASSISTANT_USERNAME-কে গ্রুপে যোগ/জয়েন করাতে হবে।
"""

from pyrogram.errors import (
    UserNotParticipant,
    UserAlreadyParticipant,
    FloodWait,
    ChatAdminRequired,
    RPCError,
)

import config
from clients import bot, assistant, LOGGER


def _is_peer_error(e: Exception) -> bool:
    return isinstance(e, ValueError) and "Peer id invalid" in str(e)


async def _refresh_assistant_peers():
    try:
        async for _ in assistant.get_dialogs():
            pass
    except Exception as e:
        LOGGER.warning(f"Assistant peer রিফ্রেশ ব্যর্থ: {e}")


async def is_assistant_in_chat(chat_id: int) -> bool:
    """
    Assistant এই চ্যাটের সদস্য কি না, সরাসরি চেক করে।

    Assistant `in_memory=True` সেশন ব্যবহার করে, তাই বট রিস্টার্ট হলে
    তার peer/access_hash ক্যাশে খালি হয়ে যায়। যদি assistant সেই
    গ্রুপে নিজে কোনো আপডেট না পায় (শুধু VC জয়েন করে), তাহলে pyrogram
    `get_chat_member` কলে "Peer id invalid" ValueError দেয় — এমনকি
    assistant গ্রুপে থাকলেও, তাই ভুলভাবে "নেই" বলে দিত। সমাধান: এই
    এরর এলে একবার ডায়ালগ রিফ্রেশ করে (যা সব peer আবার ক্যাশে নিয়ে আসে)
    আবার চেষ্টা করা হয়।
    """
    try:
        await assistant.get_chat_member(chat_id, "me")
        return True
    except UserNotParticipant:
        return False
    except Exception as e:
        if _is_peer_error(e):
            LOGGER.info("Assistant peer ক্যাশে ছিল না — ডায়ালগ রিফ্রেশ করে আবার চেষ্টা।")
            await _refresh_assistant_peers()
            try:
                await assistant.get_chat_member(chat_id, "me")
                return True
            except UserNotParticipant:
                return False
            except Exception as e2:
                LOGGER.warning(f"Assistant সদস্যপদ চেক ব্যর্থ (রিট্রাইয়ের পরেও): {e2}")
                return False
        LOGGER.warning(f"Assistant সদস্যপদ চেক ব্যর্থ: {e}")
        return False


async def ensure_assistant_in_chat(chat_id: int):
    """
    Assistant চ্যাটে আছে কি না নিশ্চিত করে, আর না থাকলে জয়েন
    করানোর পূর্ণ চেষ্টা করে।

    Returns: (joined: bool, reason: str)
        joined=True  -> assistant এখন চ্যাটে আছে, VC জয়েন করা যাবে।
        joined=False -> হয়নি; `reason` বলে কেন (caller এটি দিয়ে
                         user-facing মেসেজ বানাতে পারে)।
    """
    if await is_assistant_in_chat(chat_id):
        return True, ""

    try:
        chat = await bot.get_chat(chat_id)
    except Exception as e:
        LOGGER.warning(f"get_chat ব্যর্থ (assistant জয়েনের আগে): {e}")
        chat = None

    # --- চেষ্টা ১: পাবলিক গ্রুপ -> ইউজারনেম দিয়ে সরাসরি জয়েন -----------
    if chat and chat.username:
        try:
            await assistant.join_chat(chat.username)
            LOGGER.info(f"Assistant পাবলিক গ্রুপ @{chat.username}-এ জয়েন হয়েছে।")
            return True, ""
        except UserAlreadyParticipant:
            return True, ""
        except FloodWait as e:
            LOGGER.warning(f"Assistant জয়েন FloodWait: {e.value}s")
            return False, "flood_wait"
        except RPCError as e:
            LOGGER.warning(f"Assistant ইউজারনেম জয়েন ব্যর্থ: {e}")

    # --- চেষ্টা ২: প্রাইভেট গ্রুপ -> বট ইনভাইট লিংক বানায়, assistant সেটি দিয়ে জয়েন করে
    try:
        link = getattr(chat, "invite_link", None) if chat else None
        if not link:
            link = await bot.export_chat_invite_link(chat_id)
        if link:
            try:
                await assistant.join_chat(link)
                LOGGER.info(f"Assistant ইনভাইট লিংক দিয়ে চ্যাট {chat_id}-এ জয়েন হয়েছে।")
                return True, ""
            except UserAlreadyParticipant:
                return True, ""
    except ChatAdminRequired:
        LOGGER.warning("বট অ্যাডমিন নয় — ইনভাইট লিংক এক্সপোর্ট করা যায়নি।")
    except FloodWait as e:
        LOGGER.warning(f"Assistant জয়েন FloodWait: {e.value}s")
        return False, "flood_wait"
    except Exception as e:
        LOGGER.warning(f"Assistant ইনভাইট-লিংক জয়েন ব্যর্থ: {e}")

    # --- চেষ্টা ৩: বট নিজেই assistant-কে গ্রুপে যোগ করে (অধিকার থাকলে)
    try:
        me_assistant = await assistant.get_me()
        await bot.add_chat_members(chat_id, me_assistant.id)
        # add_chat_members সাথে সাথে নিশ্চিত করে না, তাই আবার যাচাই করো
        if await is_assistant_in_chat(chat_id):
            LOGGER.info(f"বট assistant-কে চ্যাট {chat_id}-এ যোগ করেছে।")
            return True, ""
    except Exception as e:
        LOGGER.warning(f"বট add_chat_members(assistant) ব্যর্থ: {e}")

    return False, "manual_needed"