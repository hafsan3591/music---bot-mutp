import os
import asyncio
import aiohttp
from youtube_search import YoutubeSearch

NEXOR_STREAM_URL = os.environ.get("NEXOR_STREAM_URL", "https://nexor-yt-pannl.lovable.app")
NEXOR_STREAM_KEY = os.environ.get("NEXOR_STREAM_KEY", "NEXOR_3481fsghsh62ghs")

# API-এর গান তৈরি করতে সময় লাগে — ৩ মিনিট পর্যন্ত অপেক্ষা করা হয়।
DOWNLOAD_TIMEOUT = int(os.environ.get("DOWNLOAD_TIMEOUT", "180"))



async def search_youtube(query: str):
    """YouTube-এ সার্চ করে, প্রথম ফলাফল দেয় (raw dict, লাইব্রেরি ফরম্যাট)।"""
    loop = asyncio.get_event_loop()

    def _search():
        results = YoutubeSearch(query, max_results=1).to_dict()
        return results[0] if results else None

    return await loop.run_in_executor(None, _search)


async def search_track(query: str):
    """search_youtube-এর normalized wrapper — id/title/duration/thumbnail/url দেয়।"""
    result = await search_youtube(query)
    if not result:
        return None

    thumbnails = result.get("thumbnails") or []
    video_id = result.get("id")

    return {
        "id": video_id,
        "title": result.get("title", "Unknown"),
        "duration": result.get("duration", ""),
        "thumbnail": thumbnails[0] if thumbnails else None,
        "channel": result.get("channel") or result.get("uploader") or "",
        "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
    }


class DownloadError(Exception):
    """API থেকে গান ডাউনলোড/রেডি করা যায়নি।"""


def _video_id(video: str) -> str:
    """পুরো YouTube লিংক বা আইডি — দুটো থেকেই শুধু video id বের করে (API-এর id দরকার)।"""
    video = (video or "").strip()
    if not video:
        return ""
    if "youtu.be/" in video:
        video = video.split("youtu.be/")[1]
    elif "v=" in video:
        video = video.split("v=")[1]
    elif "/shorts/" in video:
        video = video.split("/shorts/")[1]
    elif "/embed/" in video:
        video = video.split("/embed/")[1]
    for sep in ("?", "&", "/", "#"):
        video = video.split(sep)[0]
    return video


async def get_stream_url(video: str) -> str:
    """
    Nexor stream API থেকে সরাসরি স্ট্রিমিং url বানায়:
    https://nexor-yt-pannl.lovable.app/stream/<video_id>?key=<NEXOR_STREAM_KEY>

    এই API অডিও সরাসরি স্ট্রিম করে (কোনো redirect/json নয়, সরাসরি
    audio/mpeg response), তাই আমাদের ফাইল ডাউনলোড করে রাখার দরকার
    নেই — এই URL-ই সরাসরি AudioPiped-কে দেওয়া হয় আর ffmpeg নিজেই
    ধীরে ধীরে স্ট্রিম করে নেয়। শুধু একবার connect করে নিশ্চিত করা
    হয় যে video id বৈধ এবং API জবাব দিচ্ছে (পুরো body না পড়ে),
    না হলে DownloadError।
    """
    video_id = _video_id(video)
    if not video_id:
        raise DownloadError("Video id পাওয়া যায়নি")

    stream_url = f"{NEXOR_STREAM_URL}/stream/{video_id}?key={NEXOR_STREAM_KEY}"
    timeout = aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT, sock_connect=30)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(stream_url) as resp:
                if resp.status != 200:
                    raise DownloadError(f"API অপ্রত্যাশিত response দিয়েছে: {resp.status}")
                # শুধু এটুকু নিশ্চিত করা দরকার ছিল যে স্ট্রিম পাওয়া যাচ্ছে — পুরো
                # অডিও এখানে ডাউনলোড করা হয় না, তাই body না পড়েই
                # `async with` connection close করে দেবে।
    except asyncio.TimeoutError:
        raise DownloadError("Stream API timeout — একটু পরে চেষ্টা করো")
    except aiohttp.ClientError as e:
        raise DownloadError(f"API-তে পৌঁছানো যায়নি: {e}")

    return stream_url


async def get_related_track(title: str, exclude_id: str = None):
    """
    Autoplay-এর জন্য — বর্তমান গানের নাম থেকে মিলতে পারে এমন পরের গান খোঁজে
    (YouTube-এর autoplay-এর মতো)। একই ভিডিও যেন আবার না আসে সেজন্য
    `exclude_id` স্কিপ করা হয়।
    """
    loop = asyncio.get_event_loop()
    base = (title or "").split("|")[0].split("(")[0].strip()
    if not base:
        return None

    def _search():
        try:
            return YoutubeSearch(f"{base} song", max_results=8).to_dict()
        except Exception:
            return []

    results = await loop.run_in_executor(None, _search)
    for result in results or []:
        video_id = result.get("id")
        if not video_id or video_id == exclude_id:
            continue
        thumbnails = result.get("thumbnails") or []
        return {
            "id": video_id,
            "title": result.get("title", "Unknown"),
            "duration": result.get("duration", ""),
            "thumbnail": thumbnails[0] if thumbnails else None,
            "channel": result.get("channel") or result.get("uploader") or "",
            "url": f"https://www.youtube.com/watch?v={video_id}",
        }
    return None