import re
from urllib.parse import urlparse

from ..config import YT_DLP_ENABLED
from .platforms import PlatformEmbedProvider, extractor_inspect


class TikTokProvider(PlatformEmbedProvider):
    def __init__(self):
        super().__init__("TikTok", ("tiktok.com",))

    def valid_path(self, url: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if host.startswith(("vm.", "vt.")):
            return bool(re.fullmatch(r"/[A-Za-z0-9_-]+/?", parsed.path))
        return bool(
            re.fullmatch(r"/@[\w.-]+/(?:video|photo)/\d+/?", parsed.path)
            or re.fullmatch(r"/t/[A-Za-z0-9_-]+/?", parsed.path)
            or re.fullmatch(r"/(?:v|embed(?:/v2)?)/\d+(?:\.html)?/?", parsed.path)
        )

    async def inspect(self, url: str) -> dict:
        result = super().resolve(url).as_dict()
        result.update({"metadata_available": False, "title": None, "thumbnail": None, "duration": None,
                       "format": None, "resolution": None, "video_codec": None, "audio_codec": None,
                       "size": None, "formats": [], "media_access": "not_checked", "_media_url": None})
        if result["status"] == "invalid_url":
            return result
        if YT_DLP_ENABLED:
            return await extractor_inspect(result, url, self.name)
        result.update({"status": "embed_only", "media_access": "not_provided_by_tiktok",
                       "message": "TikTok tidak menyediakan file sumber video untuk konversi.",
                       "next_step": "Unggah file video yang kamu miliki."})
        return result


__all__ = ["TikTokProvider"]
