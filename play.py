import random
import time

from pyrogram import filters, StopPropagation
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
)
from pytgcalls.types.input_stream import AudioPiped
from pytgcalls.exceptions import NoActiveGroupCall

import config
import db
import music_queue as q
import progress
import botstate
from clients import bot, assistant, call_py, LOGGER, START_TIME
from youtube import search_track, get_stream_url
from helpers import (
    smallcaps_title,
    random_processing_text,
    fancy_italic,
    duration_to_seconds,
    format_uptime,
    expandable_quote,
    strip_quotes,
    smallcaps,
    DIVIDER,
    bullet_lines,
)

from nowplaying import generate_now_playing_card
from assistant_join import ensure_assistant_in_chat

OWNER_FILTER = filters.user(config.OWNER_ID) if config.OWNER_ID else filters.create(lambda _, __, ___: False)

ADMIN_STATUSES = (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)

# /addvd চালানোর পরে মালিকের পরের image/video/gif-এর অপেক্ষা করা হয় (প্রাইভেট start মেসেজ)
_pending_addvd = set()

# /addvd2 চালানোর পরে মালিকের পরের image/video/gif-এর অপেক্ষা করা হয় (GROUP start মেসেজ)
_pending_addvd2 = set()

_SEND_MEDIA_MAP_NAME = {"photo": "send_photo", "video": "send_video", "animation": "send_animation"}


# ---------------------------------------------------------------------------
# Peer cache হেল্পার — "Peer id invalid" এরর এড়ানোর জন্য।
# Assistant অ্যাকাউন্ট যখন কোনো চ্যাটে সরাসরি কোনো আপডেট পায় না
# (শুধু VC জয়েন করে), তখন pyrogram তার peer/access_hash ক্যাশে করতে পারে না
# এবং পরে change_stream/leave_group_call ফেল করে। তাই এরর এলে একবার
# ডায়ালগ রিফ্রেশ করে আবার চেষ্টা করা হয়।
# ---------------------------------------------------------------------------
async def _refresh_assistant_peers():
    try:
        async for _ in assistant.get_dialogs():
            pass
    except Exception as e:
        LOGGER.warning(f"Peer রিফ্রেশ ব্যর্থ: {e}")


def _is_peer_error(e: Exception) -> bool:
    return isinstance(e, ValueError) and "Peer id invalid" in str(e)


# ---------------------------------------------------------------------------
# অ্যাডমিন / মালিক চেক — /skip /pause /resume /stop /reload শুধু গ্রুপ অ্যাডমিন
# বা বট OWNER_ID-এর জন্য। সাধারণ ইউজার শুধু /play ব্যবহার করতে পারে।
# ---------------------------------------------------------------------------
async def _is_group_admin(client, chat_id: int, user_id: int) -> bool:
    if config.OWNER_ID and user_id == config.OWNER_ID:
        return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in ADMIN_STATUSES
    except Exception:
        return False


ADMIN_ONLY_TEXT = f"❌ {smallcaps_title('এই কমান্ড শুধু গ্রুপ অ্যাডমিন বা মালিক ব্যবহার করতে পারেন')}."

NOT_YOUR_REQUEST_TEXT = (
    f"❌ {smallcaps_title('এটি আপনার রিকোয়েস্ট নয়')}!\n"
    f"{smallcaps_title('শুধু যে এই গানটি রিকোয়েস্ট করেছে, বা গ্রুপের অ্যাডমিন/মালিক এটিকে নিয়ন্ত্রণ করতে পারবেন')}."
)


# ---------------------------------------------------------------------------
# কন্ট্রোল-অনুমতি চেক — /skip /pause /resume /stop (এবং এদের inline বাটন)
# শুধু ৩ জন ব্যবহার করতে পারে: যে বর্তমান ট্র্যাক রিকোয়েস্ট করেছিল, গ্রুপ
# অ্যাডমিন, বা বট মালিক। বাকি সাধারণ ইউজারদের NOT_YOUR_REQUEST_TEXT দেখানো হয়।
# ---------------------------------------------------------------------------
async def _can_control(client, chat_id: int, user_id: int) -> bool:
    if await _is_group_admin(client, chat_id, user_id):
        return True
    track = q.get_now_playing(chat_id)
    return bool(track and track.get("requested_by_id") == user_id)


ASSISTANT_NOT_JOINED_TEXT = (
    f"❌ **{smallcaps_title('আমার assistant অ্যাকাউন্ট এই গ্রুপে নেই')}!**\n\n"
    f"{smallcaps_title('মিউজিক বাজানোর জন্য assistant অ্যাকাউন্টকে গ্রুপে থাকতে হবে')}.\n"
    f"👉 @{config.ASSISTANT_USERNAME} {smallcaps_title('কে গ্রুপে যোগ করো, বা এটিকে গ্রুপ জয়েন করাও')}.\n\n"
    f"{smallcaps_title('তারপর আবার')} `/play` {smallcaps_title('করো')}."
)

ASSISTANT_FLOOD_TEXT = (
    f"⏳ {smallcaps_title('টেলিগ্রাম কিছুক্ষণের জন্য রেট-লিমিট দিয়েছে, একটু পরে আবার চেষ্টা করো')}."
)


# ---------------------------------------------------------------------------
# মালিক: /on /off — পুরো বট চালু/বন্ধ করার গ্লোবাল সুইচ।
# OFF থাকলে বট কোনো মেসেজ/বাটনের জবাব দেয় না, শুধু /on /off
# চালু থাকে। DB-তে persist হয়, তাই রিস্টার্টের পরেও সেই স্ট্যাটাস মনে থাকে।
# ---------------------------------------------------------------------------
@bot.on_message(filters.command("on") & OWNER_FILTER)
async def on_command(client, message: Message):
    botstate.set_enabled(True)
    await db.set_bot_status(True)
    await message.reply_text(f"✅ {smallcaps_title('বট চালু করা হয়েছে')}.")


@bot.on_message(filters.command("off") & OWNER_FILTER)
async def off_command(client, message: Message):
    botstate.set_enabled(False)
    await db.set_bot_status(False)
    await message.reply_text(
        f"🔴 {smallcaps_title('বট বন্ধ করা হয়েছে')}.\n"
        f"{smallcaps_title('এখন শুধু')} `/on` {smallcaps_title('কাজ করবে')}."
    )


def _off_blocker(_, __, message: Message) -> bool:
    if botstate.is_enabled():
        return False
    text = message.text or message.caption or ""
    # /on এবং /off সবসময় চলা উচিত, বট OFF থাকলেও
    return not text.startswith(("/on", "/off"))


def _off_blocker_cb(_, __, cq: CallbackQuery) -> bool:
    return not botstate.is_enabled()


# group=-1 -> এই হ্যান্ডলার সবার আগে চলে; OFF থাকলে এর থেকে সামনে আর
# কোনো হ্যান্ডলারের কাছে মেসেজ/কলব্যাক পৌঁছায়ই না (StopPropagation)।
@bot.on_message(filters.create(_off_blocker), group=-1)
async def _blocked_while_off(client, message: Message):
    raise StopPropagation


@bot.on_callback_query(filters.create(_off_blocker_cb), group=-1)
async def _blocked_cb_while_off(client, cq: CallbackQuery):
    await cq.answer(smallcaps_title("বট এখন off"), show_alert=True)
    raise StopPropagation


def _btn(text: str, *, style: str = None, **kwargs) -> InlineKeyboardButton:
    """
    InlineKeyboardButton বানায়। Telegram Bot API 9.4 (৯ ফেব্রুয়ারি ২০২৬)-এর
    রঙিন বাটন (style="primary"/"success"/"danger") শুধু তখনই দেখাবে
    যখন তোমার pyrogram/kurigram/pyrofork লাইব্রেরি এটি সাপোর্ট করে —
    না করলে কোনো এরর ছাড়াই সাধারণ (রঙহীন) বাটন হয়ে যায়। এতে পুরনো বট
    কখনো ক্র্যাশ করবে না, আর লাইব্রেরি আপডেট করলে রঙ নিজে থেকেই আসবে।
    """
    if style:
        try:
            return InlineKeyboardButton(text, style=style, **kwargs)
        except TypeError:
            pass
    return InlineKeyboardButton(text, **kwargs)


def _controls_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                _btn("▶️", callback_data="m_resume", style="success"),
                _btn("⏸", callback_data="m_pause", style="primary"),
                _btn("🔁", callback_data="m_replay", style="primary"),
                _btn("⏭", callback_data="m_skip", style="primary"),
                _btn("⏹", callback_data="m_stop", style="danger"),
            ],
            [_btn(f"⊙ {smallcaps_title('close')} ⊙", callback_data="m_close", style="danger")],
        ]
    )





def _start_keyboard(bot_username: str):
    return InlineKeyboardMarkup(
        [
            [
                _btn(
                    f"➕ {smallcaps_title('আমাকে তোমার গ্রুপে যোগ করো')}",
                    url=f"https://t.me/{bot_username}?startgroup=true",
                    style="success",
                )
            ],
            [
                _btn(f"👑 {smallcaps_title('মালিক')}", url=config.OWNER_URL, style="primary"),
                _btn(f"🛠 {smallcaps_title('সাপোর্ট')}", url=config.SUPPORT_URL, style="primary"),
            ],
            [
                _btn(f"📢 {smallcaps_title('চ্যানেল')}", url=config.CHANNEL_URL, style="primary"),
                _btn(f"❓ {smallcaps_title('সাহায্য')}", callback_data="help_menu", style="primary"),
            ],
        ]
    )


def _help_keyboard():
    return InlineKeyboardMarkup(
        [[_btn(f"🔙 {smallcaps_title('ফিরে যাও')}", callback_data="back_to_start", style="primary")]]
    )


async def _safe_quote_send(action, text: str):
    """
    মেসেজ পাঠায়/এডিট করে expandable quote সহ। যদি তোমার
    pyrogram/kurigram বিল্ড `<blockquote expandable>` সাপোর্ট না করে, তাহলে
    কোনো ক্র্যাশ ছাড়াই সেই মেসেজ সাধারণ (quote ছাড়া) চলে যায় — টেক্সট স্টাইল
    ঠিক একই থাকে।
    """
    try:
        return await action(text)
    except Exception as e:
        LOGGER.warning(f"Quote পাঠানো ব্যর্থ, সাধারণ fallback: {e}")
        return await action(strip_quotes(text))


async def _send_welcome(chat_id: int, text: str, reply_markup, media: dict = None):
    """প্রদত্ত মিডিয়া (photo/video/gif) সহ বা শুধু টেক্সট সহ welcome পাঠায়।"""
    if media:
        send_func = getattr(bot, _SEND_MEDIA_MAP_NAME.get(media["media_type"], "send_photo"))
        try:
            return await _safe_quote_send(
                lambda t: send_func(chat_id, media["file_id"], caption=t, reply_markup=reply_markup),
                text,
            )
        except Exception as e:
            LOGGER.warning(f"Start মিডিয়া পাঠানো ব্যর্থ, টেক্সট fallback: {e}")
    return await _safe_quote_send(
        lambda t: bot.send_message(chat_id, t, reply_markup=reply_markup, disable_web_page_preview=True),
        text,
    )


async def _edit_body(cq_message, text: str, reply_markup):
    """Callback-এ মেসেজ এডিট করে — সেটি মিডিয়া ক্যাপশন হোক বা সাধারণ টেক্সট।"""
    if cq_message.photo or cq_message.video or cq_message.animation:
        await _safe_quote_send(lambda t: cq_message.edit_caption(t, reply_markup=reply_markup), text)
    else:
        await _safe_quote_send(
            lambda t: cq_message.edit_text(t, reply_markup=reply_markup, disable_web_page_preview=True),
            text,
        )



HELP_TEXT = (
    "🦋 **ᴀᴠᴀɪʟᴀʙʟᴇ ᴄᴏᴍᴍᴀɴᴅs**\n\n"
    "`/play <song>` — গান বাজাও বা কিউতে দাও\n"
    "`/skip` — পরের গান _(শুধু অ্যাডমিন)_\n"
    "`/pause` — পজ করো _(শুধু অ্যাডমিন)_\n"
    "`/resume` — রিজিউম করো _(শুধু অ্যাডমিন)_\n"
    "`/stop` — বন্ধ করো _(শুধু অ্যাডমিন)_\n"
    "`/reload` — বট রিফ্রেশ করো _(শুধু অ্যাডমিন)_\n"
    "`/id` — নিজের/গ্রুপের আইডি দেখো"
)


def _welcome_text(user_name: str, user_id: int, bot_name: str, bot_username: str) -> str:
    user_tag = f"[{smallcaps_title(user_name)}](tg://user?id={user_id})"
    bot_tag = f"[{fancy_italic(bot_name)}](https://t.me/{bot_username})"
    # বডি একটি expandable quote-এর ভেতরে যায় — স্ক্রিনশট/ভিডিও-র মতো ইফেক্ট:
    # ট্যাপ করে এক্সপ্যান্ড হয় আর ভেতরেই স্ক্রল হয়। টেক্সট স্টাইল একই থাকে।
    body = (
        f"🦋 ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ {bot_tag}\n"
        f"『 ᴘʀᴇᴍɪᴜᴍ ✧ ᴀᴅ-ꜰʀᴇᴇ ✧ ᴜʟᴛʀᴀ sᴍᴏᴏᴛʜ 』\n\n"
        f"🦋 ʜɪɢʜ • Qᴜᴀʟɪᴛʏ • ᴍᴜsɪᴄ • ʙᴏᴛ\n"
        f"ғᴏʀ ᴛᴇʟᴇɢʀᴀᴍ ɢʀᴏᴜᴘs & ᴄʜᴀɴɴᴇʟs\n\n"
        f"🦋✦ ɪɴsᴛᴀɴᴛ sᴛʀᴇᴀᴍɪɴɢ\n"
        f"🦋✦ ᴜʟᴛʀᴀ sᴍᴏᴏᴛʜ ᴘʟᴀʏʙᴀᴄᴋ\n"
        f"🦋✦ ᴄʀʏsᴛᴀʟ ᴄʟᴇᴀʀ sᴏᴜɴᴅ • ɴᴏ ʟᴀɢ\n\n"
        f"🦋✦ ᴛᴀᴘ ʜᴇʟᴘ ᴛᴏ ᴠɪᴇᴡ ᴀʟʟ ᴄᴏᴍᴍᴀɴᴅs\n\n"
        f"🦋ᴘᴏᴡᴇʀᴇᴅ ʙʏ : [Aᴅɪᴛʏᴀ × Aᴘɪꜱ](https://t.me/AdityaXzexxyAPI)\n\n"
        f"╭───────────── ✦ ─────────────╮\n"
        f"❖ ᴇɴᴊᴏʏ ᴛʜᴇ ᴍᴜsɪᴄ ❖\n"
        f"╰───────────── ✦ ─────────────╯"
    )
    return f"🦋 ʜᴇʏ {user_tag}..!! ✦\n\n" + expandable_quote(body)



def _group_start_text(bot_name: str) -> str:
    """গ্রুপে /start-এর মেসেজ — মিউজিক বটের কাজের কুইক ইনফো সহ।"""
    return f"✨ {fancy_italic(bot_name)} ɪs ᴏɴʟɪɴᴇ ᴀɴᴅ ʀᴇᴀᴅʏ ✨\n\n" + expandable_quote(
        "🎧 ᴍᴜsɪᴄ ᴘᴀɴᴇʟ\n"
        "╰┈➤ /play <sᴏɴɢ ɴᴀᴍᴇ> — গান বাজাও\n"
        "╰┈➤ /skip • /pause • /resume • /stop\n"
        "╰┈➤ /queue — পরের গানগুলোর লিস্ট\n\n"
        "⌾ ᴄᴏɴᴛʀᴏʟ : ᴀᴅᴍɪɴs ᴀɴᴅ ʀᴇǫᴜᴇsᴛᴇʀ ᴏɴʟʏ\n"
        "⌾ ǫᴜᴀʟɪᴛʏ : ʜɪɢʜ ᴅᴇғɪɴɪᴛɪᴏɴ ᴀᴜᴅɪᴏ\n\n"
        "•── ⋅ ⋅  ────── ⋅᯽⋅ ────── ⋅ ⋅ ⋅──•"
    )


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------
@bot.on_message(filters.command("start"))
async def start_cmd(client, message: Message):
    await db.add_user(message.from_user.id)
    me = await bot.get_me()

    if message.chat.type != "private":
        # গ্রুপে /start — আলাদা মেসেজ, আলাদা মিডিয়া (/addvd2 দিয়ে সেট), লাইভ uptime
        await db.add_chat(message.chat.id)
        media = await db.get_group_start_media()
        await _send_welcome(
            message.chat.id,
            _group_start_text(me.first_name),
            _start_keyboard(me.username),
            media,
        )
    else:
        # প্রাইভেট /start — পুরনো welcome মেসেজ, পুরনো মিডিয়া (/addvd দিয়ে সেট)
        media = await db.get_start_media()
        await _send_welcome(
            message.chat.id,
            _welcome_text(message.from_user.first_name, message.from_user.id, me.first_name, me.username),
            _start_keyboard(me.username),
            media,
        )

    # মালিককে জানাও কে বট ব্যবহার করল (প্রাইভেট চ্যাটে)
    if message.chat.type == "private" and config.OWNER_ID and message.from_user.id != config.OWNER_ID:
        try:
            await bot.send_message(
                config.OWNER_ID,
                f"👤 বট ব্যবহার করেছে:\n"
                f"নাম: {message.from_user.first_name}\n"
                f"ইউজারনেম: @{message.from_user.username}\n"
                f"আইডি: `{message.from_user.id}`",
            )
        except Exception as e:
            LOGGER.warning(f"মালিককে জানানো ব্যর্থ: {e}")


@bot.on_callback_query(filters.regex("^help_menu$"))
async def help_menu_cb(client, cq: CallbackQuery):
    await cq.answer()
    await _edit_body(cq.message, HELP_TEXT, _help_keyboard())


@bot.on_callback_query(filters.regex("^back_to_start$"))
async def back_to_start_cb(client, cq: CallbackQuery):
    await cq.answer()
    me = await bot.get_me()
    if cq.message.chat.type != "private":
        text = _group_start_text(me.first_name)
    else:
        text = _welcome_text(cq.from_user.first_name, cq.from_user.id, me.first_name, me.username)
    await _edit_body(cq.message, text, _start_keyboard(me.username))


# ---------------------------------------------------------------------------
# বটকে গ্রুপে যোগ করা
# ---------------------------------------------------------------------------
@bot.on_message(filters.new_chat_members)
async def added_to_group(client, message: Message):
    me = await bot.get_me()
    if not any(u.id == me.id for u in message.new_chat_members):
        return

    await db.add_chat(message.chat.id)
    adder = message.from_user.first_name if message.from_user else "there"

    await message.reply_text(
        f"🎉 ʜᴇʏ **{adder}**!\n\n"
        f"ᴛʜᴀɴᴋ ʏᴏᴜ ғᴏʀ ᴀᴅᴅɪɴɢ **[{me.first_name}](https://t.me/{me.username})** ɪɴ {message.chat.title}.\n\n"
        f"🎶 **{me.first_name}** ɪs ɴᴏᴡ ʀᴇᴀᴅʏ ᴛᴏ sᴛʀᴇᴀᴍ ᴍᴜsɪᴄ, ᴍᴀɴᴀɢᴇ ᴄʜᴀᴛs ᴀɴᴅ ᴅᴇʟɪᴠᴇʀ ᴛʜᴇ ʙᴇsᴛ ᴇxᴘᴇʀɪᴇɴᴄᴇ.",
        reply_markup=_start_keyboard(me.username),
        disable_web_page_preview=True,
    )


# ---------------------------------------------------------------------------
# /play — সবাই ব্যবহার করতে পারে
# ---------------------------------------------------------------------------
@bot.on_message(filters.command("play") & filters.group)
async def play_command(client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            f"❌ {smallcaps_title('গানের নামও লেখো')}!\nExample: `/play Aaj Ki Raat`"
        )

    query = message.text.split(None, 1)[1]
    chat_id = message.chat.id
    requester = message.from_user.mention if message.from_user else "Someone"
    requester_id = message.from_user.id if message.from_user else None

    # প্রথমে নিশ্চিত করো assistant অ্যাকাউন্ট এই গ্রুপে আছে — না থাকলে
    # VC জয়েনই হবে না। নিজে জয়েন করানোর চেষ্টা এখানেই হয়।
    joined, reason = await ensure_assistant_in_chat(chat_id)
    if not joined:
        if reason == "flood_wait":
            return await message.reply_text(ASSISTANT_FLOOD_TEXT)
        return await message.reply_text(ASSISTANT_NOT_JOINED_TEXT)

    status = await message.reply_text(random_processing_text())

    track = await search_track(query)
    if not track:
        return await status.edit_text(f"❌ {smallcaps_title('কিছু পাওয়া যায়নি, অন্য নাম চেষ্টা করো')}.")

    # নতুন API গান ডাউনলোড করে দেয় — একটু সময় লাগে, তাই এখানে তখন
    # পর্যন্ত অপেক্ষা করা হয় যতক্ষণ গানটি তৈরি না হয় (সর্বোচ্চ ৩ মিনিট)।
    try:
        await status.edit_text(f"⏳ {smallcaps_title('গান ডাউনলোড হচ্ছে, একটু অপেক্ষা করো')}...")
    except Exception:
        pass

    try:
        stream_url = await get_stream_url(track["id"])
    except Exception as e:
        LOGGER.error(f"Stream URL এরর: {e}")
        return await status.edit_text(
            f"❌ {smallcaps_title('ডাউনলোড এরর')} — "
            f"{smallcaps_title('গান লোড করা যায়নি, একটু পরে চেষ্টা করো বা অন্য গান পাঠাও')}."
        )


    track["stream_url"] = stream_url
    track["requested_by"] = requester
    track["requested_by_id"] = requester_id

    # যদি আগে থেকেই কিছু বাজছে -> কিউতে দিয়ে দাও
    if q.is_playing(chat_id):
        position = q.push(chat_id, track)
        await status.delete()
        await message.reply_text(
            f"🎵 {smallcaps_title('কিউতে যোগ করা হয়েছে')} #{position}\n"
            f"📝 {smallcaps_title('টাইটেল')} : {track['title']}\n"
            f"🕐 {smallcaps_title('সময়কাল')} : {track['duration']} ᴍɪɴᴜᴛᴇs\n"
            f"👤 {smallcaps_title('রিকোয়েস্ট')} : {requester}"
        )
        return

    await status.delete()
    await _start_playing(chat_id, track, message)


async def _start_playing(chat_id: int, track: dict, message: Message):
    """VC জয়েন/চেঞ্জ করে ট্র্যাক বাজায় এবং Now Playing কার্ড পাঠায়।"""
    try:
        try:
            await call_py.join_group_call(chat_id, AudioPiped(track["stream_url"]))
        except NoActiveGroupCall:
            return await message.reply_text(
                f"❌ **{smallcaps_title('ভয়েস চ্যাট চালু নেই')}!**\n\n"
                f"{smallcaps_title('প্রথমে গ্রুপে ভয়েস চ্যাট শুরু করো')}:\n"
                "Group Settings → Voice Chat → Start Voice Chat\n\n"
                f"{smallcaps_title('তারপর')} `/play` {smallcaps_title('আবার পাঠাও')}."
            )
        except Exception as e:
            if _is_peer_error(e):
                await _refresh_assistant_peers()
            try:
                await call_py.change_stream(chat_id, AudioPiped(track["stream_url"]))
            except Exception as e2:
                LOGGER.error(f"প্লে এরর: {e2}")
                return await message.reply_text(
                    f"❌ **{smallcaps_title('বাজানো যায়নি')}**\n\n"
                    f"{smallcaps_title('ভয়েস চ্যাট চালু আছে কি না একবার দেখে নাও, তারপর আবার চেষ্টা করো')}."
                )

        q.set_now_playing(chat_id, track)
        await _send_now_playing(chat_id, track, message)

    except Exception as e:
        LOGGER.error(f"_start_playing গুরুতর এরর: {e}")
        await message.reply_text(f"❌ {smallcaps_title('কিছু একটা গোলমাল হয়েছে, আবার চেষ্টা করো')}.")


def _now_playing_caption(track: dict) -> str:
    # স্ক্রিনশটের ফ্যান্সি স্টাইল + expandable quote (ট্যাপ করে এক্সপ্যান্ড/স্ক্রল)।
    artists = [a.strip() for a in str(track.get("channel") or "").replace("-", ",").split(",") if a.strip()]
    if not artists:
        artists = [track.get("requested_by", "Unknown")]

    body = (
        f"» 『 {smallcaps_title(track['title'])} 』\n"
        f"{bullet_lines(smallcaps_title(a) for a in artists)}\n\n"
        f"⌾ {smallcaps_title('সময়কাল')} : {track['duration']}\n"
        f"⌾ {smallcaps_title('দ্বারা')} : {track.get('requested_by', 'Unknown')}\n\n"
        f"{DIVIDER}"
    )
    return f"❖ {smallcaps_title('Now Playing')}..!! ✦\n\n" + expandable_quote(body)


async def _send_now_playing(chat_id: int, track: dict, message: Message = None, edit_message: Message = None):
    """
    Now Playing কার্ড পাঠায়। যদি `edit_message` দেওয়া হয় (যেমন skip
    বাটন থেকে), তাহলে নতুন মেসেজ পাঠানো/পুরনো ডিলিট করার বদলে সেই
    মেসেজই in-place আপডেট হয়ে যায় — এতে কার্ড কখনো "গায়েব" হয় না,
    শুধু নিজে থেকে রিফ্রেশ হয়।
    """
    caption = _now_playing_caption(track)
    card = await generate_now_playing_card(track.get("thumbnail"), track["title"], track["duration"])
    markup = _controls_keyboard()
    media = card or track.get("thumbnail")

    sent = None

    if edit_message is not None:
        try:
            if media:
                sent = await edit_message.edit_media(InputMediaPhoto(media, caption=caption), reply_markup=markup)
            else:
                sent = await edit_message.edit_text(caption, reply_markup=markup, disable_web_page_preview=True)
        except Exception as e:
            LOGGER.warning(f"Now playing in-place এডিট ব্যর্থ, নতুন মেসেজ পাঠাচ্ছি: {e}")

    if sent is None:
        try:
            if media:
                sent = await _safe_quote_send(
                    lambda t: bot.send_photo(chat_id, media, caption=t, reply_markup=markup), caption
                )
            elif message is not None:
                sent = await _safe_quote_send(
                    lambda t: message.reply_text(t, reply_markup=markup, disable_web_page_preview=True), caption
                )
            else:
                sent = await _safe_quote_send(
                    lambda t: bot.send_message(chat_id, t, reply_markup=markup, disable_web_page_preview=True),
                    caption,
                )
        except Exception as e:
            LOGGER.warning(f"Now playing কার্ড পাঠানো ব্যর্থ: {e}")
            plain = strip_quotes(caption)
            if message is not None:
                sent = await message.reply_text(plain, reply_markup=markup, disable_web_page_preview=True)
            else:
                sent = await bot.send_message(chat_id, plain, reply_markup=markup, disable_web_page_preview=True)


    # 🎚️ লাইভ প্রোগ্রেস বার শুরু — গানের সাথে 00:00 থেকে duration পর্যন্ত নিজে
    # থেকে এগিয়ে যাবে, যেমন স্ক্রিনশটে দেখা গিয়েছিল।
    if sent is not None:
        total_sec = duration_to_seconds(track.get("duration"))
        progress.start(chat_id, track["id"])
        progress.start_updater(
            chat_id, sent,
            lambda: _now_playing_caption(track),
            _controls_keyboard,
            track["id"], total_sec,
        )

    return sent


# ---------------------------------------------------------------------------
# স্ট্রিম শেষ হলে কিউ থেকে পরের গান
# ---------------------------------------------------------------------------
@call_py.on_stream_end()
async def on_stream_end(client, update):
    chat_id = update.chat_id
    next_track = q.pop_next(chat_id)

    if not next_track:
        q.set_now_playing(chat_id, None)
        progress.clear(chat_id)
        try:
            await call_py.leave_group_call(chat_id)
        except Exception as e:
            LOGGER.warning(f"অটো লিভ ব্যর্থ: {e}")
        return


    try:
        try:
            await call_py.change_stream(chat_id, AudioPiped(next_track["stream_url"]))
        except Exception as e:
            if _is_peer_error(e):
                await _refresh_assistant_peers()
            await call_py.join_group_call(chat_id, AudioPiped(next_track["stream_url"]))

        q.set_now_playing(chat_id, next_track)
        await _send_now_playing(chat_id, next_track)
    except Exception as e:
        LOGGER.error(f"অটো-প্লে পরের এরর: {e}")


# ---------------------------------------------------------------------------
# /skip /pause /resume /stop — শুধু গ্রুপ অ্যাডমিন/মালিক
# ---------------------------------------------------------------------------
@bot.on_message(filters.command("skip") & filters.group)
async def skip_command(client, message: Message):
    if not await _can_control(client, message.chat.id, message.from_user.id):
        return await message.reply_text(NOT_YOUR_REQUEST_TEXT)

    chat_id = message.chat.id
    next_track = q.pop_next(chat_id)
    if not next_track:
        q.set_now_playing(chat_id, None)
        progress.clear(chat_id)
        try:
            await call_py.leave_group_call(chat_id)
        except Exception:
            pass
        return await message.reply_text(f"⏭ {smallcaps_title('কিউ খালি, VC থেকে বেরিয়ে গেলাম')}.")

    try:
        await call_py.change_stream(chat_id, AudioPiped(next_track["stream_url"]))
    except Exception as e:
        if _is_peer_error(e):
            await _refresh_assistant_peers()
        try:
            await call_py.join_group_call(chat_id, AudioPiped(next_track["stream_url"]))
        except Exception as e2:
            LOGGER.error(f"Skip এরর: {e2}")
            return await message.reply_text(f"❌ {smallcaps_title('স্কিপ করা যায়নি, আবার চেষ্টা করো')}.")

    q.set_now_playing(chat_id, next_track)
    await _send_now_playing(chat_id, next_track, message)


@bot.on_message(filters.command("pause") & filters.group)
async def pause_command(client, message: Message):
    if not await _can_control(client, message.chat.id, message.from_user.id):
        return await message.reply_text(NOT_YOUR_REQUEST_TEXT)
    try:
        await call_py.pause_stream(message.chat.id)
        q.set_state(message.chat.id, "paused")
        progress.pause(message.chat.id)
        await message.reply_text(f"⏸ {smallcaps_title('পজ করা হয়েছে')}.")
    except Exception as e:
        await message.reply_text(f"❌ {e}")


@bot.on_message(filters.command("resume") & filters.group)
async def resume_command(client, message: Message):
    if not await _can_control(client, message.chat.id, message.from_user.id):
        return await message.reply_text(NOT_YOUR_REQUEST_TEXT)
    try:
        await call_py.resume_stream(message.chat.id)
        q.set_state(message.chat.id, "playing")
        progress.resume(message.chat.id)
        await message.reply_text(f"▶️ {smallcaps_title('রিজিউম করা হয়েছে')}.")
    except Exception as e:
        await message.reply_text(f"❌ {e}")


@bot.on_message(filters.command(["stop", "end"]) & filters.group)
async def stop_command(client, message: Message):
    if not await _can_control(client, message.chat.id, message.from_user.id):
        return await message.reply_text(NOT_YOUR_REQUEST_TEXT)
    try:
        await call_py.leave_group_call(message.chat.id)
    except Exception:
        pass
    q.clear(message.chat.id)
    progress.clear(message.chat.id)
    await message.reply_text(f"⏹️ {smallcaps_title('ভয়েস চ্যাট বন্ধ করা হয়েছে')}.")


# ---------------------------------------------------------------------------
# /reload — শুধু গ্রুপ অ্যাডমিন/মালিক। চেক করে বট নিজে অ্যাডমিন কি না।
# ---------------------------------------------------------------------------
@bot.on_message(filters.command("reload") & filters.group)
async def reload_command(client, message: Message):
    if not await _is_group_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text(ADMIN_ONLY_TEXT)

    me = await bot.get_me()
    try:
        bot_member = await client.get_chat_member(message.chat.id, me.id)
        is_bot_admin = bot_member.status in ADMIN_STATUSES
    except Exception as e:
        LOGGER.warning(f"Reload অ্যাডমিন-চেক ব্যর্থ: {e}")
        is_bot_admin = False

    if is_bot_admin:
        await message.reply_text(f"✅ {smallcaps_title('সফলভাবে রিলোড হয়েছে')}.")
    else:
        await message.reply_text(
            f"❌ {smallcaps_title('প্রথমে আমাকে গ্রুপ অ্যাডমিন বানাও, তারপর')} `/reload` {smallcaps_title('করো')}."
        )


# ---------------------------------------------------------------------------
# Inline বাটন (Now Playing কার্ডের নিচে)
# ---------------------------------------------------------------------------

@bot.on_callback_query(filters.regex("^m_"))
async def controls_callback(client, cq: CallbackQuery):
    chat_id = cq.message.chat.id
    action = cq.data

    # Skip/pause/resume/stop বাটন — কমান্ডের মতোই অনুমতি চেক:
    # শুধু যে বর্তমান ট্র্যাক রিকোয়েস্ট করেছিল, বা গ্রুপ অ্যাডমিন/মালিক।
    if action in ("m_resume", "m_pause", "m_skip", "m_stop"):
        if not await _can_control(client, chat_id, cq.from_user.id):
            return await cq.answer(NOT_YOUR_REQUEST_TEXT, show_alert=True)


    try:
        if action == "m_resume":
            await call_py.resume_stream(chat_id)
            q.set_state(chat_id, "playing")
            progress.resume(chat_id)
            await cq.answer("▶️ রিজিউম")

        elif action == "m_pause":
            await call_py.pause_stream(chat_id)
            q.set_state(chat_id, "paused")
            progress.pause(chat_id)
            await cq.answer("⏸ পজ")

        elif action == "m_replay":
            track = q.get_now_playing(chat_id)
            if track:
                await call_py.change_stream(chat_id, AudioPiped(track["stream_url"]))
                progress.replay(chat_id)
                await cq.answer("🔁 রিপ্লে")
            else:
                await cq.answer(smallcaps_title("কিছুই বাজছে না"), show_alert=True)

        elif action == "m_skip":
            await cq.answer("⏭ স্কিপ")
            next_track = q.pop_next(chat_id)
            if not next_track:
                q.set_now_playing(chat_id, None)
                progress.clear(chat_id)
                await call_py.leave_group_call(chat_id)
                try:
                    await cq.message.edit_reply_markup(None)
                except Exception:
                    pass
                await cq.message.reply_text(f"⏭ {smallcaps_title('কিউ খালি, VC থেকে বেরিয়ে গেলাম')}.")
            else:
                await call_py.change_stream(chat_id, AudioPiped(next_track["stream_url"]))
                q.set_now_playing(chat_id, next_track)
                # নতুন মেসেজ পাঠানোর বদলে সেই কার্ড in-place আপডেট হয়ে যায়
                # (_send_now_playing নিজেই নতুন ট্র্যাকের প্রোগ্রেস বার শুরু করে দেয়)
                await _send_now_playing(chat_id, next_track, edit_message=cq.message)

        elif action == "m_stop":
            await call_py.leave_group_call(chat_id)
            q.clear(chat_id)
            progress.clear(chat_id)
            await cq.answer("⏹ থামানো")
            try:
                await cq.message.edit_reply_markup(None)
            except Exception:
                pass
            await cq.message.reply_text(f"⏹️ {smallcaps_title('ভয়েস চ্যাট বন্ধ করা হয়েছে')}.")

        elif action == "m_close":

            await cq.answer()
            progress.cancel_task(chat_id)
            await cq.message.delete()

    except Exception as e:
        LOGGER.warning(f"Callback এরর ({action}): {e}")
        await cq.answer(f"❌ {e}", show_alert=True)


# ---------------------------------------------------------------------------
# মালিক: /addvd /delvd — /start মেসেজের সাথে যাওয়া image/video/gif
# ---------------------------------------------------------------------------
@bot.on_message(filters.command("addvd") & OWNER_FILTER)
async def addvd_command(client, message: Message):
    _pending_addvd.add(message.from_user.id)
    await message.reply_text(
        f"🖼 {smallcaps_title('এখন একটি image, video বা gif পাঠাও — সেটাই এখন থেকে PRIVATE start মেসেজের সাথে সবাইকে যাবে')}."
    )


@bot.on_message(filters.command("delvd") & OWNER_FILTER)
async def delvd_command(client, message: Message):
    await db.delete_start_media()
    _pending_addvd.discard(message.from_user.id)
    await message.reply_text(f"🗑 {smallcaps_title('প্রাইভেট start মেসেজ মিডিয়া সরিয়ে ফেলা হয়েছে')}.")


@bot.on_message(filters.command("addvd2") & OWNER_FILTER)
async def addvd2_command(client, message: Message):
    _pending_addvd2.add(message.from_user.id)
    await message.reply_text(
        f"🖼 {smallcaps_title('এখন একটি image, video বা gif পাঠাও — সেটাই এখন থেকে GROUP start মেসেজের সাথে সবাইকে যাবে')}."
    )


@bot.on_message(filters.command("delvd2") & OWNER_FILTER)
async def delvd2_command(client, message: Message):
    await db.delete_group_start_media()
    _pending_addvd2.discard(message.from_user.id)
    await message.reply_text(f"🗑 {smallcaps_title('গ্রুপ start মেসেজ মিডিয়া সরিয়ে ফেলা হয়েছে')}.")


@bot.on_message(
    (filters.photo | filters.video | filters.animation)
    & OWNER_FILTER
    & filters.create(
        lambda _, __, m: bool(m.from_user)
        and (m.from_user.id in _pending_addvd or m.from_user.id in _pending_addvd2)
    )
)
async def addvd_receive(client, message: Message):
    is_group_variant = message.from_user.id in _pending_addvd2
    _pending_addvd.discard(message.from_user.id)
    _pending_addvd2.discard(message.from_user.id)

    if message.photo:
        file_id, media_type = message.photo.file_id, "photo"
    elif message.video:
        file_id, media_type = message.video.file_id, "video"
    elif message.animation:
        file_id, media_type = message.animation.file_id, "animation"
    else:
        return

    if is_group_variant:
        await db.set_group_start_media(file_id, media_type)
        await message.reply_text(f"✅ {smallcaps_title('গ্রুপ start মেসেজ মিডিয়া সেট হয়েছে')}.")
    else:
        await db.set_start_media(file_id, media_type)
        await message.reply_text(f"✅ {smallcaps_title('প্রাইভেট start মেসেজ মিডিয়া সেট হয়েছে')}.")


# ---------------------------------------------------------------------------
# মালিক: /broadcast
# ---------------------------------------------------------------------------
@bot.on_message(filters.command("broadcast") & OWNER_FILTER)
async def broadcast_command(client, message: Message):
    if len(message.command) < 2 and not message.reply_to_message:
        return await message.reply_text(
            f"❌ {smallcaps_title('ব্রডকাস্টের জন্য মেসেজ দাও')}!\nExample: `/broadcast Hello everyone`"
        )

    text = message.text.split(None, 1)[1] if len(message.command) > 1 else None
    users = await db.get_all_users()
    status = await message.reply_text(f"📢 {smallcaps_title('ব্রডকাস্ট করা হচ্ছে')} {len(users)} {smallcaps_title('জনকে')}...")

    sent, failed = 0, 0
    for uid in users:
        try:
            if message.reply_to_message:
                await message.reply_to_message.copy(uid)
            else:
                await bot.send_message(uid, text)
            sent += 1
        except Exception:
            failed += 1

    await status.edit_text(
        f"✅ {smallcaps_title('ব্রডকাস্ট সম্পন্ন')}.\n{smallcaps_title('পাঠানো')}: {sent}\n{smallcaps_title('ব্যর্থ')}: {failed}"
    )


# ---------------------------------------------------------------------------
# /id — ইউজার এবং চ্যাট আইডি বলো
# ---------------------------------------------------------------------------
@bot.on_message(filters.command("id"))
async def id_command(client, message: Message):
    user_id = message.from_user.id if message.from_user else "Unknown"
    lines = [f"👤 **{smallcaps_title('তোমার আইডি')}:** `{user_id}`"]
    if message.chat.type != "private":
        lines.append(f"👥 **{smallcaps_title('চ্যাট আইডি')}:** `{message.chat.id}`")
    if message.reply_to_message and message.reply_to_message.from_user:
        lines.append(f"↩️ **{smallcaps_title('রিপ্লাই করা ইউজারের আইডি')}:** `{message.reply_to_message.from_user.id}`")
    await message.reply_text("\n".join(lines))