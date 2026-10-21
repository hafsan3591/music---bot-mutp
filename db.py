from clients import db, LOGGER

users_col = db["users"]
chats_col = db["chats"]
settings_col = db["settings"]

START_MEDIA_KEY = "start_media"
GROUP_START_MEDIA_KEY = "group_start_media"
BOT_STATUS_KEY = "bot_status"


async def add_user(user_id: int):
    try:
        await users_col.update_one(
            {"_id": user_id}, {"$set": {"_id": user_id}}, upsert=True
        )
    except Exception as e:
        LOGGER.warning(f"add_user DB এরর: {e}")


async def add_chat(chat_id: int):
    try:
        await chats_col.update_one(
            {"_id": chat_id}, {"$set": {"_id": chat_id}}, upsert=True
        )
    except Exception as e:
        LOGGER.warning(f"add_chat DB এরর: {e}")


async def get_all_users():
    try:
        return [doc["_id"] async for doc in users_col.find({})]
    except Exception as e:
        LOGGER.warning(f"get_all_users DB এরর: {e}")
        return []


async def get_all_chats():
    try:
        return [doc["_id"] async for doc in chats_col.find({})]
    except Exception as e:
        LOGGER.warning(f"get_all_chats DB এরর: {e}")
        return []


# ---------------------------------------------------------------------------
# /start মেসেজের সাথে যাওয়া মিডিয়া
# — প্রাইভেট চ্যাটের জন্য: মালিক /addvd /delvd
# — গ্রুপ চ্যাটের জন্য: মালিক /addvd2 /delvd2
# ---------------------------------------------------------------------------
async def _set_media(key: str, file_id: str, media_type: str):
    try:
        await settings_col.update_one(
            {"_id": key},
            {"$set": {"file_id": file_id, "media_type": media_type}},
            upsert=True,
        )
    except Exception as e:
        LOGGER.warning(f"set_media DB এরর ({key}): {e}")


async def _get_media(key: str):
    try:
        doc = await settings_col.find_one({"_id": key})
        if doc:
            return {"file_id": doc["file_id"], "media_type": doc["media_type"]}
        return None
    except Exception as e:
        LOGGER.warning(f"get_media DB এরর ({key}): {e}")
        return None


async def _delete_media(key: str):
    try:
        await settings_col.delete_one({"_id": key})
    except Exception as e:
        LOGGER.warning(f"delete_media DB এরর ({key}): {e}")


async def set_start_media(file_id: str, media_type: str):
    await _set_media(START_MEDIA_KEY, file_id, media_type)


async def get_start_media():
    return await _get_media(START_MEDIA_KEY)


async def delete_start_media():
    await _delete_media(START_MEDIA_KEY)


async def set_group_start_media(file_id: str, media_type: str):
    await _set_media(GROUP_START_MEDIA_KEY, file_id, media_type)


async def get_group_start_media():
    return await _get_media(GROUP_START_MEDIA_KEY)


async def delete_group_start_media():
    await _delete_media(GROUP_START_MEDIA_KEY)


# ---------------------------------------------------------------------------
# বটের গ্লোবাল ON/OFF স্ট্যাটাস (মালিক: /on /off) — রিস্টার্টের পরেও মনে
# থাকে, কারণ এটি DB-তে persist হয়।
# ---------------------------------------------------------------------------
async def set_bot_status(is_on: bool):
    try:
        await settings_col.update_one(
            {"_id": BOT_STATUS_KEY},
            {"$set": {"is_on": is_on}},
            upsert=True,
        )
    except Exception as e:
        LOGGER.warning(f"set_bot_status DB এরর: {e}")


async def get_bot_status() -> bool:
    try:
        doc = await settings_col.find_one({"_id": BOT_STATUS_KEY})
        if doc is None:
            return True
        return bool(doc.get("is_on", True))
    except Exception as e:
        LOGGER.warning(f"get_bot_status DB এরর: {e}")
        return True


# ---------------------------------------------------------------------------
# প্রতি-চ্যাট AUTOPLAY সেটিং (Now Playing -> ⚙️ Bot Settings -> Toggle Autoplay)
# ON থাকলে কিউ শেষ হওয়ার পরেও বট নিজে থেকে related পরের গান বাজাতে
# থাকে — ঠিক YouTube-এর autoplay-এর মতো।
# ---------------------------------------------------------------------------
AUTOPLAY_KEY = "autoplay"


async def set_autoplay(chat_id: int, value: bool):
    try:
        await settings_col.update_one(
            {"_id": f"{AUTOPLAY_KEY}:{chat_id}"},
            {"$set": {"enabled": bool(value)}},
            upsert=True,
        )
    except Exception as e:
        LOGGER.warning(f"set_autoplay DB এরর: {e}")


async def get_autoplay(chat_id: int) -> bool:
    try:
        doc = await settings_col.find_one({"_id": f"{AUTOPLAY_KEY}:{chat_id}"})
        if doc is None:
            return False
        return bool(doc.get("enabled", False))
    except Exception as e:
        LOGGER.warning(f"get_autoplay DB এরর: {e}")
        return False