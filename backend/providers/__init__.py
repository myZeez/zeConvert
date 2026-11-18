"""URL source providers used to classify and authorize media processing."""

from .registry import classify_url

__all__ = ["classify_url"]
