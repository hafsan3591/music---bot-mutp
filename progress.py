"""
Now Playing মেসেজের ভেতরে LIVE প্রোগ্রেস বার চালায় — প্রতি কয়েক সেকেন্ড
পরে caption এডিট করে elapsed সময় + বার এগিয়ে নেয়, ঠিক যেমন
স্ক্রিনশটে "00:35 ▬▬▬▬▬▬▬▬▬▬ 4:38" দেখা যাচ্ছিল।

বার নিজে থেকে এগিয়ে যায় যতক্ষণ না:
  - গান duration-এ পৌঁছে যায় (শেষ),
  - ট্র্যাক skip/stop/replay না হয়,
  - বা pause না করা হয় (তখন বার যেখানে ছিল সেখানেই থেমে যায়)।
"""

import asyncio
import time

from clients import LOGGER
from helpers import format_duration

UPDATE_INTERVAL = 10          # সেকেন্ড — Telegram flood-wait এড়াতে এতটাই নিরাপদ
BAR_LENGTH = 12
FILLED_CHAR = "▰"
EMPTY_CHAR = "▱"
MAX_EDIT_FAILURES = 3         # এতবার এডিট ফেল হলে টাস্ক নিজেই বন্ধ হয়ে যায়

# chat_id -> {"start": monotonic ts, "paused_at": ts|None, "paused_total": float, "video_id": str}
_progress: dict[int, dict] = {}

# chat_id -> background asyncio.Task যা caption আপডেট করতে থাকে
_tasks: dict[int, asyncio.Task] = {}


def _now() -> float:
    return time.monotonic()


def start(chat_id: int, video_id: str):
    """নতুন ট্র্যাক শুরু হলে elapsed-time ট্র্যাকিং (০ থেকে) রিসেট করে।"""
    _progress[chat_id] = {
        "start": _now(),
        "paused_at": None,
        "paused_total": 0.0,
        "video_id": video_id,
    }


def pause(chat_id: int):
    """বারকে যেখানে এখন আছে সেখানেই থামিয়ে দেয়।"""
    p = _progress.get(chat_id)
    if p and p["paused_at"] is None:
        p["paused_at"] = _now()


def resume(chat_id: int):
    """পজের সময় যতক্ষণ থেমে ছিল, সেটাকে elapsed গণনা থেকে বাদ রাখে।"""
    p = _progress.get(chat_id)
    if p and p["paused_at"] is not None:
        p["paused_total"] += _now() - p["paused_at"]
        p["paused_at"] = None


def replay(chat_id: int):
    """বারকে 00:00 থেকে আবার শুরু করে (🔁 বাটনের জন্য)।"""
    p = _progress.get(chat_id)
    if p:
        p["start"] = _now()
        p["paused_at"] = None
        p["paused_total"] = 0.0


def elapsed(chat_id: int) -> float:
    """এখন পর্যন্ত কত সময় গেছে (সেকেন্ডে), pause-এর সময় ধরতে না দিয়ে।"""
    p = _progress.get(chat_id)
    if not p:
        return 0.0
    ref = p["paused_at"] if p["paused_at"] is not None else _now()
    return max(0.0, ref - p["start"] - p["paused_total"])


def cancel_task(chat_id: int):
    """শুধু background updater বন্ধ করে (ট্র্যাকিং ডেটা ছোঁয়া হয় না)।"""
    task = _tasks.pop(chat_id, None)
    if task and not task.done():
        task.cancel()


def clear(chat_id: int):
    """ট্র্যাক/সেশন পুরোপুরি শেষ — ট্র্যাকিং + updater দুটোই বন্ধ।"""
    _progress.pop(chat_id, None)
    cancel_task(chat_id)


def render_bar(elapsed_sec: float, total_sec: int) -> str:
    total_sec = max(total_sec, 1)
    ratio = min(max(elapsed_sec / total_sec, 0.0), 1.0)
    filled = int(round(ratio * BAR_LENGTH))
    bar = FILLED_CHAR * filled + EMPTY_CHAR * (BAR_LENGTH - filled)
    return f"`{format_duration(int(elapsed_sec))}` {bar} `{format_duration(int(total_sec))}`"


def start_updater(chat_id: int, message, caption_fn, markup_fn, video_id: str, total_sec: int):
    """
    Background টাস্ক চালু করে যা প্রতি UPDATE_INTERVAL সেকেন্ড পর
    `message`-এর caption এডিট করে নতুন প্রোগ্রেস বার দেখায়।

    - `caption_fn()` -> বর্তমান "Now Playing" caption টেক্সট (প্রোগ্রেস বার ছাড়া)
    - `markup_fn()`  -> inline keyboard (বাটনগুলো যেমন ছিল তেমনই থাকে)
    - ট্র্যাক পরিবর্তন/স্টপ/duration-শেষ হলে এটি নিজেই থেমে যায়।
    """
    cancel_task(chat_id)

    if total_sec <= 0:
        return  # duration-ই জানা না থাকলে বার দেখানোর লাভ নেই

    async def _runner():
        failures = 0
        try:
            while True:
                await asyncio.sleep(UPDATE_INTERVAL)

                p = _progress.get(chat_id)
                if not p or p.get("video_id") != video_id:
                    return  # ট্র্যাক বদলেছে, skip/stop হয়েছে, বা replay/নতুন ট্র্যাক শুরু হয়েছে

                el = min(elapsed(chat_id), total_sec)
                try:
                    text = f"{caption_fn()}\n\n{render_bar(el, total_sec)}"
                    await message.edit_caption(text, reply_markup=markup_fn())
                    failures = 0
                except Exception as e:
                    if "MESSAGE_NOT_MODIFIED" in str(e):
                        pass
                    else:
                        failures += 1
                        LOGGER.warning(f"প্রোগ্রেস বার আপডেট ব্যর্থ ({failures}): {e}")
                        if failures >= MAX_EDIT_FAILURES:
                            return

                if el >= total_sec:
                    return
        except asyncio.CancelledError:
            pass

    _tasks[chat_id] = asyncio.create_task(_runner())


def seek(chat_id: int, position: float):
    """
    ⏪ -10s / ⏩ +10s বাটনের জন্য — বারকে সরাসরি `position` সেকেন্ডে
    সেট করে দেয় (pause স্টেট যেমন ছিল তেমনই থাকে)।
    """
    p = _progress.get(chat_id)
    if not p:
        return
    position = max(0.0, position)
    p["start"] = _now() - position
    p["paused_total"] = 0.0
    if p["paused_at"] is not None:
        p["paused_at"] = _now()