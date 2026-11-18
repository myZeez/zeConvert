from dataclasses import dataclass
import aiohttp
import asyncio
import os
from urllib.parse import urlparse

from .base import ProviderResult


@dataclass(frozen=True)
class PlatformEmbedProvider:
    name: str
    domains: tuple[str, ...]

    def matches(self, host: str) -> bool:
        return any(host == domain or host.endswith(f".{domain}") for domain in self.domains)

    def valid_path(self, url: str) -> bool:
        return True

    def resolve(self, url: str) -> ProviderResult:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.username or parsed.password or not self.valid_path(url):
            return ProviderResult(self.name, "invalid_platform_url", "invalid_url", False, False,
                                  f"Format link {self.name} tidak dikenali atau tidak aman.",
                                  "Salin URL postingan publik yang valid, atau unggah file media hasil ekspor.")
        return ProviderResult(
            provider=self.name,
            source_type="platform_page",
            status="embed_only",
            can_embed=True,
            can_process=False,
            message=f"Ini URL halaman {self.name}. Embed tidak membuktikan file sumber dapat diakses; provider akan memeriksa metadata dan akses resmi yang tersedia.",
            next_step="Jika akses media resmi tidak tersedia untuk video ini, unggah file hasil ekspor yang boleh kamu gunakan.",
        )

    async def inspect(self, url: str) -> dict:
        return {
            "provider": self.name, "source_type": "platform_page", "status": "embed_only",
            "can_embed": True, "can_process": False, "metadata_available": False, "media_access": "not_checked",
            "title": None, "thumbnail": None, "duration": None, "format": None,
            "resolution": None, "video_codec": None, "audio_codec": None, "size": None,
            "formats": [], "message": f"Metadata {self.name} tidak tersedia melalui konfigurasi aplikasi saat ini.",
            "next_step": "Coba lagi dengan koneksi integrasi resmi yang telah diotorisasi atau unggah file hasil ekspor.",
            "_media_url": None,
        }


async def extractor_inspect(result: dict, url: str, name: str) -> dict:
    """Fill `result` from yt-dlp metadata so the platform link can be converted directly."""
    from .. import ytdlp
    try:
        info = await ytdlp.fetch_info(url)
    except RuntimeError as error:
        result.update({"status": "metadata_unavailable", "message": f"Video {name} tidak dapat dibaca: {error}",
                       "next_step": "Pastikan postingan publik dan masih tersedia, atau unggah file milikmu."})
        return result
    result.update({"metadata_available": True, "title": info.get("title") or info.get("description"), "thumbnail": info.get("thumbnail"),
                   "author": info.get("uploader"), "duration": info.get("duration"),
                   "video_id": info.get("id"), "webpage_url": info.get("webpage_url"),
                   "status": "media_available", "can_process": True, "media_access": "extractor",
                   "message": "Video terdeteksi dan siap dikonversi.",
                   "next_step": "Pilih MP4 atau MP3 lalu tekan Proses media. Gunakan hanya untuk konten yang boleh kamu simpan."})
    return result


async def graph_get(path: str, *, params: dict | None = None, token: str | None = None, host: str = "graph.facebook.com") -> dict:
    token = (token or os.getenv("META_GRAPH_ACCESS_TOKEN", "")).strip()
    if not token:
        raise RuntimeError("Integrasi resmi Meta belum dikonfigurasi.")
    version = os.getenv("META_GRAPH_API_VERSION", "v26.0").strip()
    if not version.startswith("v") or not version[1:].replace(".", "").isdigit():
        raise RuntimeError("META_GRAPH_API_VERSION tidak valid.")
    if host not in {"graph.facebook.com", "graph.instagram.com"}:
        raise RuntimeError("Host Graph API tidak diizinkan.")
    url = f"https://{host}/{version}/{path.lstrip('/')}"
    timeout = aiohttp.ClientTimeout(total=15, connect=8)
    async with aiohttp.ClientSession(timeout=timeout, trust_env=False,
                                     headers={"Authorization": f"Bearer {token}"}) as session:
        try:
            async with session.get(url, params=params or {}, allow_redirects=False) as response:
                try:
                    data = await response.json(content_type=None)
                except (ValueError, aiohttp.ContentTypeError):
                    data = {}
                if response.status >= 400:
                    error = data.get("error", {}) if isinstance(data, dict) else {}
                    raise RuntimeError(f"Meta Graph API menolak akses (HTTP {response.status}, kode {error.get('code', 'unknown')}). Periksa izin akun dan aplikasi.")
                if not isinstance(data, dict):
                    raise RuntimeError("Respons Meta Graph API tidak valid.")
                return data
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            raise RuntimeError("Meta Graph API tidak dapat dijangkau saat ini.") from error


