from dataclasses import asdict, dataclass
from typing import Any, Protocol
from urllib.parse import urlparse


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    source_type: str
    status: str
    can_embed: bool
    can_process: bool
    message: str
    next_step: str

    def as_dict(self) -> dict:
        return asdict(self)


class MediaProvider(Protocol):
    name: str

    def matches(self, host: str) -> bool: ...

    def resolve(self, url: str) -> ProviderResult: ...

    async def inspect(self, url: str) -> dict[str, Any]: ...


def safe_host(url: str) -> str:
    try:
        parsed = urlparse(url)
        return (parsed.hostname or "").rstrip(".").lower()
    except ValueError:
        return ""
