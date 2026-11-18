import re
import os
from urllib.parse import parse_qs, urlparse

from ..config import YT_DLP_ENABLED
from .platforms import PlatformEmbedProvider
from .platforms import extractor_inspect, graph_get


class FacebookProvider(PlatformEmbedProvider):
    def __init__(self):
        super().__init__("Facebook", ("facebook.com", "fb.watch"))

    def valid_path(self, url: str) -> bool:
        parsed = urlparse(url)
        if (parsed.hostname or "").lower().endswith("fb.watch"):
            return bool(re.fullmatch(r"/[A-Za-z0-9_-]+/?", parsed.path))
        if parsed.path.rstrip("/") in {"/watch", "/video.php"}:
            return bool(parse_qs(parsed.query).get("v"))
        return bool(
            re.match(r"^/(?:watch|reel|reels|share(?:/[vr])?)/[A-Za-z0-9_.-]+", parsed.path)
            or re.match(r"^/[^/]+/(?:videos|posts)/", parsed.path)
        )

    def video_id(self, url: str) -> str | None:
        parsed = urlparse(url)
        query_id = parse_qs(parsed.query).get("v", [None])[0]
        if query_id and query_id.isdigit():
            return query_id
        match = re.search(r"/(?:videos|reel)/([0-9]+)(?:/|$)", parsed.path)
        return match.group(1) if match else None

    async def inspect(self, url: str) -> dict:
        base = super().resolve(url).as_dict()
        base.update({"metadata_available": False, "title": None, "thumbnail": None, "duration": None,
                     "format": None, "resolution": None, "video_codec": None, "audio_codec": None,
                     "size": None, "formats": [], "_media_url": None})
        if base["status"] == "invalid_url":
            return base
        token = os.getenv("META_GRAPH_ACCESS_TOKEN", "").strip()
        video_id = self.video_id(url)
        if YT_DLP_ENABLED and not token:
            return await extractor_inspect(base, url, self.name)
        if not token:
            base.update({"status": "embed_only", "media_access": "official_api_not_configured",
                         "message": "Embed Facebook tersedia, tetapi akses resmi Graph API belum dikonfigurasi untuk memeriksa video milik akun/Page yang diotorisasi.",
                         "next_step": "Konfigurasikan token Graph API dengan izin minimum yang sesuai, atau unggah file hasil ekspor yang kamu miliki."})
            return base
        if not video_id:
            base.update({"status": "metadata_unavailable", "media_access": "video_id_unresolved",
                         "message": "URL Facebook ini tidak menyediakan ID video yang bisa diperiksa langsung oleh Graph API.",
                         "next_step": "Gunakan permalink video yang dapat diakses oleh akun/Page terhubung, atau unggah file ekspor."})
            return base
        try:
            data = await graph_get(video_id, params={"fields": "id,description,length,source,picture,permalink_url"}, token=token)
        except RuntimeError as error:
            base.update({"status": "provider_access_denied", "media_access": "official_api_error",
                         "message": str(error), "next_step": "Pastikan token dibuat lewat OAuth resmi dan akun memiliki izin atas video tersebut."})
            return base
        source_url = data.get("source")
        if source_url and not (urlparse(source_url).scheme == "https" and urlparse(source_url).hostname):
            source_url = None
        base.update({"metadata_available": True, "title": data.get("description") or f"Video Facebook {video_id}",
                     "thumbnail": data.get("picture"), "duration": data.get("length"),
                     "status": "media_available" if source_url else "metadata_only",
                     "media_access": "authorized_graph_api" if source_url else "no_file_source",
                     "can_process": bool(source_url), "_media_url": source_url,
                     "formats": [{"container": "Sumber Graph API"}] if source_url else [],
                     "message": "File sumber video dapat diakses lewat Graph API untuk konten yang diotorisasi." if source_url else "Metadata Facebook tersedia, tetapi Graph API tidak mengembalikan sumber file untuk video ini.",
                     "next_step": "Pilih proses media untuk membuat MP4/MP3." if source_url else "Periksa izin Graph API/kepemilikan video atau unggah file hasil ekspor yang kamu miliki."})
        return base

__all__ = ["FacebookProvider"]
