import re
import asyncio
import aiohttp
from urllib.parse import parse_qs, urlparse

from ..config import YT_DLP_ENABLED
from .platforms import PlatformEmbedProvider


class YouTubeProvider(PlatformEmbedProvider):
    def __init__(self):
        super().__init__("YouTube", ("youtube.com", "youtu.be"))

    def valid_path(self, url: str) -> bool:
        parsed = urlparse(url)
        if (parsed.hostname or "").lower().endswith("youtu.be"):
            return bool(re.fullmatch(r"[\w-]{11}", parsed.path.strip("/")))
        video_id = parse_qs(parsed.query).get("v", [None])[0]
        if parsed.path.rstrip("/") == "/watch":
            return bool(video_id and re.fullmatch(r"[\w-]{11}", video_id))
        return bool(re.fullmatch(r"/(?:shorts|live|embed|v)/[\w-]{11}/?", parsed.path))

    def video_id(self, url: str) -> str | None:
        parsed = urlparse(url)
        if (parsed.hostname or "").lower().endswith("youtu.be"):
            value = parsed.path.strip("/")
            return value if re.fullmatch(r"[\w-]{11}", value) else None
        video_id = parse_qs(parsed.query).get("v", [None])[0]
        if video_id:
            return video_id if re.fullmatch(r"[\w-]{11}", video_id) else None
        match = re.fullmatch(r"/(?:shorts|live|embed|v)/([\w-]{11})/?", parsed.path)
        return match.group(1) if match else None

    async def _fetch_oembed(self, url: str) -> dict:
        timeout = aiohttp.ClientTimeout(total=12, connect=6)
        async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
            async with session.get("https://www.youtube.com/oembed", params={"url": url, "format": "json"}, allow_redirects=False) as response:
                if response.status == 404:
                    raise LookupError("YouTube tidak menyediakan metadata publik untuk URL ini.")
                if response.status >= 400:
                    raise RuntimeError(f"Endpoint metadata YouTube menjawab HTTP {response.status}.")
                return await response.json(content_type=None)

    async def inspect(self, url: str) -> dict:
        result = super().resolve(url).as_dict()
        result.update({"metadata_available": False, "title": None, "thumbnail": None, "duration": None,
                       "format": None, "resolution": None, "video_codec": None, "audio_codec": None,
                       "size": None, "formats": [], "media_access": "not_provided_by_youtube_api", "_media_url": None})
        if result["status"] == "invalid_url":
            return result
        if YT_DLP_ENABLED:
            try:
                data = await self._fetch_oembed(url)
                result.update({
                    "metadata_available": True,
                    "title": data.get("title"),
                    "thumbnail": data.get("thumbnail_url"),
                    "author": data.get("author_name"),
                    "video_id": self.video_id(url),
                    "webpage_url": url,
                    "status": "media_available",
                    "can_process": True,
                    "media_access": "extractor",
                    "message": "Video terdeteksi dan siap dikonversi.",
                    "next_step": "Pilih MP4 atau MP3 lalu tekan Proses media. Gunakan hanya untuk konten yang boleh kamu simpan.",
                })
                return result
            except (LookupError, RuntimeError, aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                pass
            from .. import ytdlp
            try:
                info = await ytdlp.fetch_info(url)
            except RuntimeError as error:
                result.update({"status": "metadata_unavailable", "message": f"Video tidak dapat dibaca: {error}",
                               "next_step": "Periksa apakah video publik dan masih tersedia, atau unggah file milikmu."})
                return result
            result.update({"metadata_available": True, "title": info.get("title"), "thumbnail": info.get("thumbnail"),
                           "author": info.get("uploader"), "duration": info.get("duration"),
                           "video_id": info.get("id") or self.video_id(url), "webpage_url": info.get("webpage_url"),
                           "status": "media_available", "can_process": True, "media_access": "extractor",
                           "message": "Video terdeteksi dan siap dikonversi.",
                           "next_step": "Pilih MP4 atau MP3 lalu tekan Proses media. Gunakan hanya untuk konten yang boleh kamu simpan."})
            return result
        try:
            data = await self._fetch_oembed(url)
        except LookupError as error:
            result.update({"status": "metadata_unavailable", "message": str(error), "next_step": "Periksa apakah video masih tersedia atau gunakan file ekspor milikmu."})
            return result
        except RuntimeError as error:
            result.update({"status": "metadata_unavailable", "message": str(error), "next_step": "Video tetap bisa dicoba melalui embed; untuk memproses media, unggah file yang boleh kamu gunakan."})
            return result
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            result.update({"status": "metadata_unavailable", "message": "Metadata YouTube tidak dapat dijangkau saat ini.", "next_step": "Coba lagi nanti atau unggah file hasil ekspor yang boleh kamu gunakan."})
            return result
        result.update({"metadata_available": True, "title": data.get("title"), "thumbnail": data.get("thumbnail_url"),
                       "author": data.get("author_name"),
                       "status": "metadata_available_embed_only", "can_process": False,
                       "media_access": "not_provided_by_youtube_api",
                       "message": "Metadata publik berhasil diperoleh. API YouTube yang tersedia untuk aplikasi ini tidak menyediakan file sumber video untuk konversi.",
                       "next_step": "Video dapat diputar melalui embed. Untuk video milikmu, unduh/ekspor lewat YouTube Studio lalu unggah file di sini."})
        return result

__all__ = ["YouTubeProvider"]
