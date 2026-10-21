import random

# স্টাইল ওভাররাইড — স্ক্রিনশটের মতো ফ্যান্সি লুক (Nσᴡ Pʟᴧʏɪηɢ / Dυʀᴧᴛɪση-এর মতো)।
# এই ৫টি অক্ষর বিশেষ গ্লিফ ব্যবহার করে, বাকি সব smallcaps-ই থাকে।
_STYLE = {"a": "ᴧ", "e": "є", "o": "σ", "n": "η", "u": "υ"}

_SMALLCAPS = {
    "a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ғ", "g": "ɢ",
    "h": "ʜ", "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ", "m": "ᴍ", "n": "ɴ",
    "o": "ᴏ", "p": "ᴘ", "q": "ǫ", "r": "ʀ", "s": "s", "t": "ᴛ", "u": "ᴜ",
    "v": "ᴠ", "w": "ᴡ", "x": "x", "y": "ʏ", "z": "ᴢ",
}

# Processing / "searching"-এর সময় দেখানো র্যান্ডম ইমোজি (শুধু ইমোজি, কোনো টেক্সট নয়)
PROCESSING_EMOJIS = ["🧪", "🦋", "🔍", "🧐"]


def smallcaps(text: str) -> str:
    """প্রতিটি অক্ষরকে smallcaps-এ বদলায় (lowercase স্টাইল — লেবেলের জন্য)।"""
    return "".join(
        _STYLE.get(ch.lower()) or _SMALLCAPS.get(ch.lower(), ch) if ch.isalpha() else ch
        for ch in text
    )


def smallcaps_title(text: str) -> str:
    """প্রতিটি শব্দের প্রথম অক্ষর সাধারণ capital, বাকি smallcaps — হেডিংয়ের জন্য।"""
    out = []
    new_word = True
    for ch in text:
        if ch.isalpha():
            out.append(
                ch.upper()
                if new_word
                else (_STYLE.get(ch.lower()) or _SMALLCAPS.get(ch.lower(), ch))
            )
            new_word = False
        else:
            out.append(ch)
            new_word = ch in " -_/\n"
    return "".join(out)


def fancy_italic(text: str) -> str:
    """A-Z/a-z-কে Mathematical Sans-Serif Bold Italic unicode-এ বদলায়
    (যেমন 𝙌𝙪𝙚𝙚𝙣 𝙭 𝙢𝙪𝙨𝙞𝙘 স্টাইল) — বাকি অক্ষর (space, emoji) যেমন ছিল তেমনই থাকে।"""
    out = []
    for ch in text:
        if "A" <= ch <= "Z":
            out.append(chr(0x1D63C + (ord(ch) - ord("A"))))
        elif "a" <= ch <= "z":
            out.append(chr(0x1D656 + (ord(ch) - ord("a"))))
        else:
            out.append(ch)
    return "".join(out)


def random_processing_text() -> str:
    """শুধু একটি র্যান্ডম ইমোজি দেয় (৩টির মধ্যে) — কোনো টেক্সট নয়।"""
    return random.choice(PROCESSING_EMOJIS)


def format_duration(seconds) -> str:
    """সেকেন্ডকে MM:SS বা H:MM:SS ফরম্যাটে বদলায়। আগে থেকেই স্ট্রিং হলে সেটাই ফেরত।"""
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return str(seconds) if seconds else "??:??"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def duration_to_seconds(duration_str: str) -> int:
    """'4:38' বা '1:04:38'-এর মতো স্ট্রিংকে সেকেন্ডে বদলায়।"""
    if not duration_str:
        return 0
    parts = str(duration_str).split(":")
    try:
        parts = [int(p) for p in parts]
    except ValueError:
        return 0
    seconds = 0
    for p in parts:
        seconds = seconds * 60 + p
    return seconds


def format_uptime(seconds) -> str:
    """সেকেন্ডকে 'ʜʜ:ᴍᴍ:ss'-এর মতো smallcaps uptime স্ট্রিং বানায়
    (যেমন '12ʜ:4ᴍ:10s') — Now Playing/গ্রুপ start মেসেজের জন্য।"""
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        seconds = 0
    h, rem = divmod(max(seconds, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{h}ʜ:{m}ᴍ:{s}s"


# ---------------------------------------------------------------------------
# Expandable quote — স্ক্রিনশট/ভিডিও-র মতো ইফেক্ট: মেসেজের বডি একটি quote
# ব্লকের ভেতরে আসে যেখানে "ক্লিক করে নিচে স্ক্রল / expand" হয়।
# Pyrogram ডিফল্ট parse mode HTML + Markdown দুটোই বোঝে, তাই বাকি
# টেক্সট স্টাইল (bold, links, smallcaps) ঠিক আগের মতোই থাকে।
# ---------------------------------------------------------------------------
def expandable_quote(text: str) -> str:
    return f"<blockquote expandable>{text}</blockquote>"


def quote(text: str) -> str:
    return f"<blockquote>{text}</blockquote>"


def strip_quotes(text: str) -> str:
    """লাইব্রেরি expandable blockquote সাপোর্ট না করলে fallback-এর জন্য।"""
    return (
        text.replace("<blockquote expandable>", "")
        .replace("<blockquote>", "")
        .replace("</blockquote>", "")
    )


# ---------------------------------------------------------------------------
# Now Playing-এর ডেকোরেটিভ ডিভাইডার (স্ক্রিনশটের মতো)
# ---------------------------------------------------------------------------
DIVIDER = "•── ⋅ ⋅  ────── ⋅᯽⋅ ────── ⋅ ⋅ ⋅──•"


def bullet_lines(items) -> str:
    """প্রতিটি আইটেমকে '╰┈➤ '-এর সাথে আলাদা লাইনে দেয়।"""
    return "\n".join(f"╰┈➤ {i}" for i in items if i)