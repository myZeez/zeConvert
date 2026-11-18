import ipaddress
from urllib.parse import urlparse

from .base import ProviderResult


class DirectMediaProvider:
    name = "direct_media"

    def matches(self, host: str) -> bool:
        return True

    def resolve(self, url: str) -> ProviderResult:
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").rstrip(".").lower()
            if parsed.scheme != "https" or not host or parsed.username or parsed.password:
                return ProviderResult(self.name, "invalid_url", "invalid_url", False, False,
                                      "URL harus HTTPS dan tidak boleh menyertakan username atau password.",
                                      "Tempel URL HTTPS langsung ke file media atau unggah file dari perangkat.")
            if host in {"localhost", "metadata.google.internal"} or host.endswith((".localhost", ".local", ".internal")):
                raise ValueError("Host lokal tidak diizinkan.")
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                address = None
            if address and not address.is_global:
                raise ValueError("Alamat IP privat atau khusus tidak diizinkan.")
            return ProviderResult(self.name, "direct_media_candidate", "requires_validation", False, True,
                                  "URL tampak seperti tautan langsung. Backend akan memeriksa host, tipe konten, dan file media sebelum memprosesnya.",
                                  "Pilih Pratinjau atau Proses media. Sumber harus bisa diakses dari server dan mengirim file audio/video.")
        except ValueError as error:
            return ProviderResult(self.name, "invalid_url", "blocked", False, False,
                                  str(error) or "URL tidak valid.",
                                  "Gunakan URL HTTPS publik langsung ke file media, atau unggah file lokal.")

__all__ = ["DirectMediaProvider"]
