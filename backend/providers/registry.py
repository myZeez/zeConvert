from .base import ProviderResult
from .direct_media import DirectMediaProvider
from .facebook import FacebookProvider
from .instagram import InstagramProvider
from .tiktok import TikTokProvider
from .youtube import YouTubeProvider

PLATFORM_PROVIDERS = (YouTubeProvider(), InstagramProvider(), FacebookProvider(), TikTokProvider())
DIRECT_PROVIDER = DirectMediaProvider()


def get_platform_provider(url: str):
    from urllib.parse import urlparse
    try:
        host = (urlparse(url).hostname or "").rstrip(".").lower()
    except ValueError:
        return None
    return next((provider for provider in PLATFORM_PROVIDERS if provider.matches(host)), None)


def classify_url(url: str) -> ProviderResult:
    if not isinstance(url, str) or not url.strip():
        return ProviderResult("none", "invalid_url", "invalid_url", False, False,
                              "URL belum diisi.", "Tempel link atau unggah file media.")
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return ProviderResult("none", "invalid_url", "invalid_url", False, False,
                              "Format URL tidak valid.", "Periksa kembali link, atau unggah file media.")
    host = (parsed.hostname or "").rstrip(".").lower()
    for provider in PLATFORM_PROVIDERS:
        if provider.matches(host):
            return provider.resolve(url.strip())
    if not host:
        return ProviderResult("none", "invalid_url", "invalid_url", False, False,
                              "URL tidak memiliki host yang valid.", "Tempel URL HTTPS langsung ke file media.")
    return DIRECT_PROVIDER.resolve(url.strip())
