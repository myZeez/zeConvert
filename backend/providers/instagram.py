import re
import os
from urllib.parse import urlparse

from ..config import YT_DLP_ENABLED
from .platforms import PlatformEmbedProvider
from .platforms import extractor_inspect, graph_get


class InstagramProvider(PlatformEmbedProvider):
    def __init__(self):
        super().__init__("Instagram", ("instagram.com",))

    def valid_path(self, url: str) -> bool:
        return bool(
            re.fullmatch(
                r"/(?:(?:[\w.-]+/)?(?:p|reel|reels|tv)|share(?:/(?:p|reel|reels))?)/[A-Za-z0-9_-]+/?",
                urlparse(url).path,
            )
        )

    async def inspect(self, url: str) -> dict:
        base = super().resolve(url).as_dict()
        base.update({"metadata_available": False, "title": None, "thumbnail": None, "duration": None,
                     "format": None, "resolution": None, "video_codec": None, "audio_codec": None,
                     "size": None, "formats": [], "_media_url": None})
        if base["status"] == "invalid_url":
            return base
        token = os.getenv("META_INSTAGRAM_ACCESS_TOKEN", "").strip()
        account_id = os.getenv("META_INSTAGRAM_USER_ID", "").strip()
        if YT_DLP_ENABLED and not (token and account_id):
            return await extractor_inspect(base, url, self.name)
        if not token or not account_id:
            base.update({"status": "embed_only", "media_access": "official_api_not_configured",
                         "message": "Embed Instagram tersedia, tetapi API resmi belum dikonfigurasi untuk memeriksa media dari akun profesional yang diotorisasi.",
                         "next_step": "Hubungkan akun Instagram profesional melalui aplikasi Meta yang diotorisasi, atau unggah file hasil ekspor yang kamu miliki."})
            return base
        if not account_id.isdigit():
            base.update({"status": "provider_configuration_error", "media_access": "invalid_account_id",
                         "message": "META_INSTAGRAM_USER_ID harus berupa ID akun numeric yang disediakan Graph API.",
                         "next_step": "Perbaiki konfigurasi akun Instagram resmi atau unggah file ekspor."})
            return base
        try:
            graph_host = os.getenv("META_INSTAGRAM_GRAPH_HOST", "graph.facebook.com").strip().lower()
            data = await graph_get(f"{account_id}/media", params={"fields": "id,caption,media_type,media_url,permalink,thumbnail_url,timestamp", "limit": "100"}, token=token, host=graph_host)
        except RuntimeError as error:
            base.update({"status": "provider_access_denied", "media_access": "official_api_error",
                         "message": str(error), "next_step": "Periksa token, izin Instagram Graph API, dan bahwa akun yang diotorisasi adalah pemilik media."})
            return base
        wanted = urlparse(url)
        wanted_host = (wanted.hostname or "").lower().removeprefix("www.")
        wanted_path = wanted.path.rstrip("/")
        matched = None
        for item in data.get("data", []):
            permalink = urlparse(item.get("permalink", ""))
            if (permalink.hostname or "").lower().removeprefix("www.") == wanted_host and permalink.path.rstrip("/") == wanted_path:
                matched = item
                break
        if not matched:
            base.update({"status": "metadata_unavailable", "media_access": "not_in_authorized_account",
                         "message": "Graph API tidak menemukan permalink ini di media akun Instagram yang diotorisasi.",
                         "next_step": "Pastikan akun terhubung adalah pemiliknya dan gunakan permalink publik yang tepat, atau unggah file ekspor."})
            return base
        source_url = matched.get("media_url") if matched.get("media_type") == "VIDEO" else None
        if source_url:
            parsed_source = urlparse(source_url)
            if parsed_source.scheme != "https" or not parsed_source.hostname:
                source_url = None
        base.update({"metadata_available": True, "title": matched.get("caption") or "Media Instagram",
                     "thumbnail": matched.get("thumbnail_url"), "status": "media_available" if source_url else "metadata_only",
                     "media_access": "authorized_graph_api" if source_url else "no_video_file_source",
                     "can_process": bool(source_url), "_media_url": source_url,
                     "formats": [{"container": "Sumber Graph API"}] if source_url else [],
                     "message": "File video akun yang diotorisasi tersedia dari Instagram Graph API." if source_url else "Metadata tersedia, tetapi media ini bukan video langsung atau API tidak memberikan URL file.",
                     "next_step": "Pilih proses media untuk membuat MP4/MP3." if source_url else "Unggah file video hasil ekspor yang kamu miliki."})
        return base

__all__ = ["InstagramProvider"]
