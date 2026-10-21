"""
প্রতিটি চ্যাটের জন্য মিউজিক কিউ এবং বর্তমানে বাজতে থাকা ট্র্যাক মেমোরিতে রাখে।
বট রিস্টার্ট হলে এটি খালি হয়ে যায় — যা ঠিকই আছে, কারণ VC-ও
রিস্টার্টের পরে আবার জয়েন করতে হবে।
"""

# chat_id -> track dict-এর লিস্ট: {video_id, title, duration, thumbnail, requested_by, stream_url}
_queues: dict[int, list] = {}

# chat_id -> বর্তমানে বাজতে থাকা track dict (বা None)
_now_playing: dict[int, dict] = {}

# chat_id -> "playing" | "paused"
_state: dict[int, str] = {}


def get_queue(chat_id: int) -> list:
    return _queues.setdefault(chat_id, [])


def push(chat_id: int, track: dict) -> int:
    """কিউয়ের শেষে ট্র্যাক যোগ করে, তার পজিশন (1-indexed) রিটার্ন করে।"""
    q = get_queue(chat_id)
    q.append(track)
    return len(q)


def pop_next(chat_id: int):
    """কিউ থেকে পরের ট্র্যাক বের করে দেয়, খালি হলে None।"""
    q = get_queue(chat_id)
    if not q:
        return None
    return q.pop(0)


def set_now_playing(chat_id: int, track):
    if track is None:
        _now_playing.pop(chat_id, None)
        _state.pop(chat_id, None)
    else:
        _now_playing[chat_id] = track
        _state[chat_id] = "playing"


def get_now_playing(chat_id: int):
    return _now_playing.get(chat_id)


def is_playing(chat_id: int) -> bool:
    return chat_id in _now_playing


def set_state(chat_id: int, state: str):
    _state[chat_id] = state


def get_state(chat_id: int) -> str:
    return _state.get(chat_id, "playing")


def clear(chat_id: int):
    _queues.pop(chat_id, None)
    _now_playing.pop(chat_id, None)
    _state.pop(chat_id, None)