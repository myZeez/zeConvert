import pytest
import asyncio

from backend.providers import classify_url
from backend.providers.youtube import YouTubeProvider
from backend.providers.facebook import FacebookProvider
from backend.providers.instagram import InstagramProvider


@pytest.mark.parametrize(("url", "provider", "status", "can_process"), [
    ("https://www.youtube.com/watch?v=abcdefghijk", "YouTube", "embed_only", False),
    ("https://www.instagram.com/reel/ABC_123/", "Instagram", "embed_only", False),
    ("https://www.youtube.com/watch/?v=abcdefghijk", "YouTube", "embed_only", False),
    ("https://www.youtube.com/v/abcdefghijk", "YouTube", "embed_only", False),
    ("https://www.instagram.com/reels/ABC_123/", "Instagram", "embed_only", False),
    ("https://www.instagram.com/user.name/reel/ABC_123/", "Instagram", "embed_only", False),
    ("https://www.instagram.com/share/reel/ABC_123/", "Instagram", "embed_only", False),
    ("https://www.facebook.com/watch/?v=12345", "Facebook", "embed_only", False),
    ("https://www.facebook.com/watch?v=12345", "Facebook", "embed_only", False),
    ("https://www.facebook.com/video.php?v=12345", "Facebook", "embed_only", False),
    ("https://www.facebook.com/share/r/abc123/", "Facebook", "embed_only", False),
    ("https://www.tiktok.com/v/7300000000000000000.html", "TikTok", "embed_only", False),
    ("https://cdn.example.test/video.mp4", "direct_media", "requires_validation", True),
    ("https://cdn.example.test/audio.mp3", "direct_media", "requires_validation", True),
    ("https://127.0.0.1/video.mp4", "direct_media", "blocked", False),
    ("not-a-url", "none", "invalid_url", False),
])
def test_provider_classifies_sources(url, provider, status, can_process):
    result = classify_url(url)
    assert (result.provider, result.status, result.can_process) == (provider, status, can_process)


@pytest.mark.parametrize("url", [
    "https://youtube.com/watch?v=bad",
    "https://instagram.com/profile/other",
    "https://facebook.com/profile.php?id=123",
])
def test_platform_providers_validate_supported_video_paths(url):
    result = classify_url(url)
    assert result.status == "invalid_url"
    assert not result.can_embed
    assert not result.can_process


def test_youtube_oembed_metadata_does_not_claim_downloadable_file(monkeypatch):
    provider = YouTubeProvider()

    async def fake_oembed(url):
        return {"title": "Public demo", "author_name": "Channel", "thumbnail_url": "https://i.ytimg.com/thumb.jpg"}

    monkeypatch.setattr(provider, "_fetch_oembed", fake_oembed)
    monkeypatch.setattr("backend.providers.youtube.YT_DLP_ENABLED", False)
    result = asyncio.run(provider.inspect("https://www.youtube.com/watch?v=abcdefghijk"))
    assert result["metadata_available"] is True
    assert result["title"] == "Public demo"
    assert result["thumbnail"].endswith("thumb.jpg")
    assert result["can_embed"] is True
    assert result["can_process"] is False
    assert result["_media_url"] is None


def test_facebook_graph_api_source_is_available_only_for_authorized_video(monkeypatch):
    provider = FacebookProvider()
    monkeypatch.setenv("META_GRAPH_ACCESS_TOKEN", "test-token")

    async def fake_graph(video_id, *, params, token):
        assert video_id == "12345"
        assert token == "test-token"
        return {"id": video_id, "source": "https://cdn.example.test/authorized.mp4", "length": 12}

    monkeypatch.setattr("backend.providers.facebook.graph_get", fake_graph)
    result = asyncio.run(provider.inspect("https://www.facebook.com/watch/?v=12345"))
    assert result["status"] == "media_available"
    assert result["can_process"] is True
    assert result["_media_url"].endswith("authorized.mp4")


def test_instagram_graph_api_matches_only_authorized_account_media(monkeypatch):
    provider = InstagramProvider()
    monkeypatch.setenv("META_INSTAGRAM_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("META_INSTAGRAM_USER_ID", "987654321")

    async def fake_graph(path, *, params, token, host):
        assert path == "987654321/media"
        assert token == "test-token"
        assert host == "graph.facebook.com"
        return {"data": [{"media_type": "VIDEO", "media_url": "https://cdn.example.test/reel.mp4",
                          "permalink": "https://www.instagram.com/reel/ABC_123/", "caption": "Owned reel"}]}

    monkeypatch.setattr("backend.providers.instagram.graph_get", fake_graph)
    result = asyncio.run(provider.inspect("https://www.instagram.com/reel/ABC_123/"))
    assert result["status"] == "media_available"
    assert result["can_process"] is True
    assert result["title"] == "Owned reel"


def test_meta_providers_report_missing_authorization_without_claiming_access(monkeypatch):
    monkeypatch.delenv("META_GRAPH_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("META_INSTAGRAM_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("META_INSTAGRAM_USER_ID", raising=False)
    monkeypatch.setattr("backend.providers.facebook.YT_DLP_ENABLED", False)
    monkeypatch.setattr("backend.providers.instagram.YT_DLP_ENABLED", False)
    facebook =asyncio.run(FacebookProvider().inspect("https://www.facebook.com/watch/?v=12345"))
    instagram = asyncio.run(InstagramProvider().inspect("https://www.instagram.com/reel/ABC_123/"))
    assert facebook["media_access"] == "official_api_not_configured"
    assert instagram["media_access"] == "official_api_not_configured"
    assert not facebook["can_process"] and not instagram["can_process"]


def test_tiktok_urls_are_recognised_and_extractor_makes_them_processable(monkeypatch):
    from backend.providers.registry import classify_url
    from backend.providers.tiktok import TikTokProvider

    assert classify_url("https://www.tiktok.com/@user.name/video/7300000000000000000").status == "embed_only"
    assert classify_url("https://vm.tiktok.com/ZSabc123/").provider == "TikTok"
    assert classify_url("https://www.tiktok.com/@user").status == "invalid_url"

    async def fake_info(url):
        return {"title": "Klip", "thumbnail": "https://example.com/t.jpg", "uploader": "user", "duration": 12}

    monkeypatch.setattr("backend.ytdlp.fetch_info", fake_info)
    monkeypatch.setattr("backend.providers.tiktok.YT_DLP_ENABLED", True)
    result = asyncio.run(TikTokProvider().inspect("https://www.tiktok.com/@user/video/7300000000000000000"))
    assert result["can_process"] and result["media_access"] == "extractor"
    monkeypatch.setattr("backend.providers.tiktok.YT_DLP_ENABLED", False)
    result = asyncio.run(TikTokProvider().inspect("https://www.tiktok.com/@user/video/7300000000000000000"))
    assert not result["can_process"]
