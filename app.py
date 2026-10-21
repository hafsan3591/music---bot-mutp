import asyncio
import threading

import aiohttp
import uvicorn
from fastapi import FastAPI
from pyrogram import idle
from pyrogram.types import BotCommand

import config
import db
import botstate
from clients import bot, assistant, call_py, LOGGER

# হ্যান্ডলার রেজিস্টার করার জন্য ইমপোর্ট করা জরুরি
import play  # noqa: F401

web = FastAPI()


@web.get("/")
async def root():
    return {"status": "running"}


def run_web():
    uvicorn.run(web, host="0.0.0.0", port=config.PORT, log_level="warning")


async def keep_alive():
    """
    Render ফ্রি ওয়েব সার্ভিস ১৫ মিনিট নিষ্ক্রিয়তার পরে ঘুমিয়ে দেয়।
    তাই বট নিজেই নিজের URL-এ পর্যায়ক্রমে পিং করে, যাতে প্রসেস কখনো
    অফলাইন না হয়। RENDER_EXTERNAL_URL ডিপ্লয়ের সময় Render নিজেই
    প্রদান করে, এটি আলাদা সেট করার দরকার নেই।
    """
    if not config.RENDER_EXTERNAL_URL:
        LOGGER.info("RENDER_EXTERNAL_URL সেট করা নেই — keep-alive পিং বাদ দেওয়া হচ্ছে।")
        return

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(config.RENDER_EXTERNAL_URL, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    LOGGER.info(f"Keep-alive পিং: {resp.status}")
            except Exception as e:
                LOGGER.warning(f"Keep-alive পিং ব্যর্থ: {e}")
            # প্রথমে পিং সাথে সাথে, তারপরে প্রতি PING_INTERVAL সেকেন্ডে —
            # Render ফ্রি টিয়ার ~১৫ মিনিট নিষ্ক্রিয়তার পরে ঘুমিয়ে দেয়,
            # তাই শুরুতেই পিং করা জরুরি, শুধু ঘুমের পরে নয়।
            await asyncio.sleep(config.PING_INTERVAL)


async def register_bot_commands():
    """বট কমান্ড সেট করে, যাতে গ্রুপে '/' লিখলে মেনু দেখা যায়।"""
    try:
        await bot.set_bot_commands(
            [
                BotCommand("start", "বট চালু করো"),
                BotCommand("play", "গান বাজাও"),
                BotCommand("skip", "পরের গান"),
                BotCommand("pause", "পজ করো"),
                BotCommand("resume", "রিজিউম করো"),
                BotCommand("stop", "বন্ধ করো"),
                BotCommand("reload", "বট রিফ্রেশ করো (শুধু অ্যাডমিন)"),
                BotCommand("id", "নিজের/গ্রুপের আইডি দেখো"),
            ]
        )
    except Exception as e:
        LOGGER.warning(f"বট কমান্ড সেট করা যায়নি: {e}")


async def _run_once():
    await bot.start()
    LOGGER.info("✅ বট চালু হয়েছে")

    await assistant.start()
    LOGGER.info("✅ অ্যাসিস্ট্যান্ট চালু হয়েছে")

    # গুরুত্বপূর্ণ: অ্যাসিস্ট্যান্টের ডায়ালগ একবার ফেচ করে নাও, যাতে pyrogram
    # প্রতিটি গ্রুপ/চ্যানেলের peer + access_hash ক্যাশে করে নেয়। এটি না করলে
    # কিছুক্ষণ পরে "ValueError: Peer id invalid: ..." আসে, যখন বট change_stream/
    # leave_group_call কোনো এমন চ্যাটে করতে চায় যার peer অ্যাসিস্ট্যান্টের
    # লোকাল ক্যাশে নেই।
    try:
        async for _ in assistant.get_dialogs():
            pass
        LOGGER.info("✅ অ্যাসিস্ট্যান্টের peer ক্যাশে হয়েছে")
    except Exception as e:
        LOGGER.warning(f"ডায়ালগ ক্যাশে করতে সমস্যা: {e}")

    await call_py.start()
    LOGGER.info("✅ PyTgCalls চালু হয়েছে — এখন বট গান বাজানোর জন্য প্রস্তুত")

    # মালিকের /on /off দিয়ে আগেরবার যে স্ট্যাটাস সেট করা হয়েছিল, সেটাই লোড করো
    try:
        botstate.set_enabled(await db.get_bot_status())
        LOGGER.info(f"✅ বট স্ট্যাটাস লোড হয়েছে: {'ON' if botstate.is_enabled() else 'OFF'}")
    except Exception as e:
        LOGGER.warning(f"বট স্ট্যাটাস লোড করা যায়নি, ডিফল্ট ON রাখা হচ্ছে: {e}")

    await register_bot_commands()

    if config.LOG_GROUP_ID:
        try:
            await bot.send_message(config.LOG_GROUP_ID, "✅ বট রিস্টার্ট হয়েছে এবং এখন অনলাইন।")
        except Exception as e:
            LOGGER.warning(f"লগ গ্রুপে মেসেজ পাঠানো যায়নি: {e}")

    keep_alive_task = asyncio.create_task(keep_alive())

    try:
        await idle()
    finally:
        keep_alive_task.cancel()
        try:
            await bot.stop()
        except Exception:
            pass
        try:
            await assistant.stop()
        except Exception:
            pass
        LOGGER.info("🛑 বট বন্ধ হয়েছে")


async def main():
    """
    _run_once() কে মুড়ে দেয়, যাতে কোনো অনাকাঙ্ক্ষিত ক্র্যাশ (নেটওয়ার্ক
    ড্রপ, কানেকশন রিসেট ইত্যাদি) বটকে স্থায়ীভাবে অফলাইন না করে —
    কিছুক্ষণ পরে প্রসেস নিজেই রিস্টার্ট হয়ে যায়, যতক্ষণ Render নিজে
    প্রসেস কিল না করে।
    """
    while True:
        try:
            await _run_once()
            break  # idle() শুধু তখনই রিটার্ন করে যখন প্রসেস স্বাভাবিকভাবে বন্ধ করা হয়
        except Exception as e:
            LOGGER.error(f"বট ক্র্যাশ হয়েছে, ১০ সেকেন্ডে রিস্টার্ট করা হচ্ছে: {e}")
            await asyncio.sleep(10)


if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    asyncio.get_event_loop().run_until_complete(main())