"""
বটের গ্লোবাল ON/OFF সুইচ — শুধু OWNER_ID `/on` এবং `/off` কমান্ড দিয়ে
নিয়ন্ত্রণ করে। যখন OFF থাকে তখন বট কোনো মেসেজ বা বাটনের জবাব দেয় না
(শুধু `/on` / `/off` চালু থাকে)।

দ্রুত in-memory ক্যাশে ব্যবহার হয় (প্রতিটি মেসেজে DB কল না করার জন্য),
কিন্তু স্টেট DB-তেও persist হয় (দেখো db.py: set_bot_status /
get_bot_status) — তাই রিস্টার্টের পরেও মনে থাকে।
"""

_enabled = True


def is_enabled() -> bool:
    return _enabled


def set_enabled(value: bool):
    global _enabled
    _enabled = bool(value)