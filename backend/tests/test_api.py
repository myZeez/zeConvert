import subprocess
import time
from pathlib import Path
import shutil
import json

import pytest
from fastapi.testclient import TestClient

from backend.config import FFMPEG, FFPROBE, UPLOAD_DIR
from backend.main import app


def media_tools_available():
    for tool in (FFMPEG, FFPROBE):
        try:
            subprocess.run([tool, "-version"], capture_output=True, timeout=5, check=True)
        except (OSError, subprocess.SubprocessError):
            return False
    return True


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def make_sample_video(path: Path):
    subprocess.run([
        FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=160x120:d=1",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-shortest", "-c:v", "libx264", "-c:a", "aac", str(path),
    ], check=True, timeout=30)


def make_non_mp4_codecs_video(path: Path):
    subprocess.run([
        FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=160x120:d=1",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-shortest", "-c:v", "mpeg4", "-c:a", "libmp3lame", str(path),
    ], check=True, timeout=30)


def wait_for_job(client, job_id, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] in {"completed", "failed", "canceled"}:
            return job
        time.sleep(0.2)
    pytest.fail("Pekerjaan tidak selesai sebelum timeout")


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_media_api_exposes_separate_classify_inspect_resolve_and_job_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    for path in ("/api/media/classify", "/api/media/inspect", "/api/media/resolve", "/api/jobs/download", "/api/jobs/convert", "/api/jobs/{job_id}/download"):
        assert path in paths


def test_frontend_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "zeConvert" in response.text


@pytest.mark.parametrize(("url", "provider", "status", "can_process"), [
    ("https://www.youtube.com/watch?v=abcdefghijk", "YouTube", "embed_only", False),
    ("https://www.instagram.com/reel/ABC_123/", "Instagram", "embed_only", False),
    ("https://www.facebook.com/watch/?v=12345", "Facebook", "embed_only", False),
    ("https://cdn.example.test/video.mp4", "direct_media", "requires_validation", True),
    ("https://127.0.0.1/private.mp4", "direct_media", "blocked", False),
    ("not-a-url", "none", "invalid_url", False),
])
def test_provider_resolution(client, url, provider, status, can_process, monkeypatch):
    if provider in {"YouTube", "Instagram", "Facebook"}:
        async def fake_inspect(url):
            return {"provider": provider, "status": status, "can_process": can_process, "source_type": "platform_page"}
        monkeypatch.setattr("backend.main.inspect_platform_source", fake_inspect)
    response = client.post("/api/media/classify", json={"url": url})
    assert response.status_code == 200
    result = response.json()
    assert result["provider"] == provider
    assert result["status"] == status
    assert result["can_process"] is can_process


def test_resolve_requires_a_verified_source_before_reporting_candidate(client, monkeypatch):
    async def verified(url):
        return {"status": "accessible", "mime_type": "video/mp4", "size": 1234,
                "filename": "clip.mp4", "duration": None, "resolution": None,
                "video_codec": None, "audio_codec": None, "formats": [],
                "metadata_available": False, "message": "Header media terdeteksi."}

    monkeypatch.setattr("backend.main.inspect_direct_media", verified)
    result = client.post("/api/media/resolve", json={"url": "https://cdn.example.test/clip.mp4"}).json()
    assert result["status"] == "accessible"
    assert result["can_process"] is True
    assert result["source"] == {"kind": "direct_url", "access": "candidate", "verification": "headers_verified", "reference": "server_managed"}


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=abcdefghijk",
    "https://www.instagram.com/reel/ABC_123/",
    "https://www.facebook.com/watch/?v=12345",
])
def test_platform_media_info_does_not_claim_file_access(client, url, monkeypatch):
    async def fake_inspect(url):
        return {"status": "embed_only", "metadata_available": False, "can_process": False,
                "provider": "platform", "formats": [], "message": "No authorized media source."}

    monkeypatch.setattr("backend.main.inspect_platform_source", fake_inspect)
    result = client.post("/api/media/info", json={"url": url}).json()
    assert result["status"] == "embed_only"
    assert result["metadata_available"] is False
    assert result["formats"] == []


def test_direct_media_info_uses_headers_without_downloading(client, monkeypatch):
    async def fake_inspect(url):
        return {"status": "accessible", "mime_type": "video/mp4", "size": 1234,
                "filename": "clip.mp4", "duration": None, "resolution": None,
                "video_codec": None, "audio_codec": None, "formats": [],
                "metadata_available": False, "message": "Header media terdeteksi."}

    monkeypatch.setattr("backend.main.inspect_direct_media", fake_inspect)
    result = client.post("/api/media/info", json={"url": "https://cdn.example.test/clip.mp4"}).json()
    assert result["status"] == "accessible"
    assert result["mime_type"] == "video/mp4"
    assert result["size"] == 1234
    assert result["duration"] is None


def test_auth_required_source_has_specific_info_status(client, monkeypatch):
    from fastapi import HTTPException

    async def auth_required(url):
        raise HTTPException(403, {"code": "source_requires_auth", "message": "Sumber meminta autentikasi.", "next_step": "Unggah file hasil ekspor resmi."})

    monkeypatch.setattr("backend.main.inspect_direct_media", auth_required)
    result = client.post("/api/media/info", json={"url": "https://cdn.example.test/locked.mp4"}).json()
    assert result["status"] == "source_requires_auth"
    assert result["can_process"] is False
    assert result["next_step"]


def test_authorized_facebook_graph_source_is_verified_before_processing(client, monkeypatch):
    monkeypatch.setenv("META_GRAPH_ACCESS_TOKEN", "test-only-token")

    async def fake_graph(video_id, *, params, token):
        assert video_id == "12345"
        assert token == "test-only-token"
        return {"id": video_id, "source": "https://cdn.example.test/authorized.mp4", "description": "Owned video"}

    async def verify_file(url):
        assert url == "https://cdn.example.test/authorized.mp4"
        return {"status": "accessible", "mime_type": "video/mp4", "size": 2048,
                "formats": [{"container": "video/mp4", "size": 2048}], "metadata_available": False,
                "message": "Verified"}

    monkeypatch.setattr("backend.providers.facebook.graph_get", fake_graph)
    monkeypatch.setattr("backend.main.inspect_direct_media", verify_file)
    response = client.post("/api/media/info", json={"url": "https://www.facebook.com/watch/?v=12345"})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "media_available"
    assert result["can_process"] is True
    assert result["media_access"] == "authorized_api_source_verified"
    assert result["size"] == 2048
    assert "_media_url" not in result


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=abcdefghijk",
    "https://www.instagram.com/p/ABC_123/",
    "https://www.facebook.com/watch/?v=12345",
])
def test_platform_pages_are_embed_only_not_sent_to_ffmpeg(client, url, monkeypatch):
    async def unavailable_official_source(url):
        return {"status": "embed_only", "can_process": False, "message": "No authorized media source.", "next_step": "Upload an export.", "_media_url": None}

    monkeypatch.setattr("backend.main.inspect_platform_source", unavailable_official_source)
    monkeypatch.setattr("backend.main.YT_DLP_ENABLED", False)
    response = client.post("/api/jobs/url", json={"url": url, "output": "mp4"})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "embed_only"
    assert "authorized media source" in detail["message"]
    assert detail["next_step"]


@pytest.mark.parametrize("url", ["http://example.com/video.mp4", "https://localhost/video.mp4", "https://127.0.0.1/video.mp4"])
def test_invalid_or_private_media_url_is_rejected(client, url):
    response = client.post("/api/jobs/url", json={"url": url, "output": "mp4"})
    assert response.status_code in (400, 422)


@pytest.mark.skipif(not media_tools_available(), reason="FFmpeg/FFprobe belum tersedia")
def test_direct_media_preview_then_convert_to_mp4(client, tmp_path, monkeypatch):
    source = tmp_path / "direct-source.mp4"
    make_sample_video(source)

    async def fake_fetch(url, destination, job_id):
        shutil.copyfile(source, destination)
        return "video/mp4", destination.stat().st_size

    monkeypatch.setattr("backend.main.fetch_direct_media", fake_fetch)
    preview = client.post("/api/previews", json={"url": "https://cdn.example.test/video.mp4"})
    assert preview.status_code == 201, preview.text
    preview_data = preview.json()
    assert preview_data["mime_type"].startswith("video/")
    assert preview_data["metadata_available"] is True
    assert preview_data["video_codec"] == "h264"
    assert preview_data["audio_codec"] == "aac"
    media_response = client.get(preview_data["player_url"])
    assert media_response.status_code == 200
    assert b"ftyp" in media_response.content[:32]

    response = client.post("/api/jobs/url", json={"preview_id": preview_data["id"], "output": "mp4"})
    assert response.status_code == 202
    job = wait_for_job(client, response.json()["id"])
    assert job["status"] == "completed", job.get("message")
    result = client.get(f"/api/jobs/{job['id']}/download")
    assert result.status_code == 200
    result_path = tmp_path / "converted.mp4"
    result_path.write_bytes(result.content)
    inspected = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,codec_name", "-of", "json", str(result_path)], capture_output=True, check=True)
    streams = json.loads(inspected.stdout)["streams"]
    assert any(item["codec_type"] == "video" and item["codec_name"] == "h264" for item in streams)
    assert any(item["codec_type"] == "audio" and item["codec_name"] == "aac" for item in streams)


@pytest.mark.skipif(not media_tools_available(), reason="FFmpeg/FFprobe belum tersedia")
def test_direct_audio_url_can_be_fetched_converted_and_downloaded(client, tmp_path, monkeypatch):
    source_video = tmp_path / "audio-source.mp4"
    make_sample_video(source_video)
    source_audio = tmp_path / "audio-source.mp3"
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source_video), "-vn", "-codec:a", "libmp3lame", str(source_audio)], check=True, timeout=30)

    async def fake_fetch(url, destination, job_id):
        assert url == "https://cdn.example.test/audio.mp3"
        shutil.copyfile(source_audio, destination)
        return "audio/mpeg", destination.stat().st_size

    monkeypatch.setattr("backend.main.fetch_direct_media", fake_fetch)
    response = client.post("/api/jobs/url", json={"url": "https://cdn.example.test/audio.mp3", "output": "mp3", "bitrate": 128})
    assert response.status_code == 202
    job = wait_for_job(client, response.json()["id"])
    assert job["status"] == "completed", job.get("message")
    result = client.get(f"/api/jobs/{job['id']}/download")
    assert result.status_code == 200
    output = tmp_path / "converted-audio.mp3"
    output.write_bytes(result.content)
    inspected = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,codec_name", "-of", "json", str(output)], capture_output=True, check=True)
    streams = json.loads(inspected.stdout)["streams"]
    assert any(item["codec_type"] == "audio" and item["codec_name"] == "mp3" for item in streams)


@pytest.mark.skipif(not media_tools_available(), reason="FFmpeg/FFprobe belum tersedia")
@pytest.mark.parametrize(("output", "extension"), [("mp4", ".mp4"), ("mp3", ".mp3")])
def test_local_upload_can_convert_to_selected_output(client, tmp_path, output, extension):
    source = tmp_path / "sample.mp4"
    make_sample_video(source)
    with source.open("rb") as media:
        response = client.post("/api/jobs/upload", files={"file": ("sample.mp4", media, "video/mp4")}, data={"output": output, "bitrate": "128"})
    assert response.status_code == 202
    job = wait_for_job(client, response.json()["id"])
    assert job["status"] == "completed", job.get("message")
    assert job["output_name"].endswith(extension)
    result = client.get(f"/api/jobs/{job['id']}/download")
    assert result.status_code == 200
    assert result.content
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 204


@pytest.mark.skipif(not media_tools_available(), reason="FFmpeg/FFprobe belum tersedia")
def test_non_compatible_video_is_reencoded_to_h264_aac(client, tmp_path):
    source = tmp_path / "legacy.avi"
    make_non_mp4_codecs_video(source)
    with source.open("rb") as media:
        response = client.post("/api/jobs/upload", files={"file": ("legacy.avi", media, "video/x-msvideo")}, data={"output": "mp4", "quality": "compact"})
    assert response.status_code == 202
    job = wait_for_job(client, response.json()["id"])
    assert job["status"] == "completed", job.get("message")
    result = client.get(f"/api/jobs/{job['id']}/download")
    output = tmp_path / "legacy-converted.mp4"
    output.write_bytes(result.content)
    inspected = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,codec_name", "-of", "json", str(output)], capture_output=True, check=True)
    codecs = {(stream["codec_type"], stream["codec_name"]) for stream in json.loads(inspected.stdout)["streams"]}
    assert ("video", "h264") in codecs
    assert ("audio", "aac") in codecs


@pytest.mark.skipif(not media_tools_available(), reason="FFmpeg/FFprobe belum tersedia")
def test_long_media_uses_parallel_segmented_processing(client, monkeypatch, tmp_path):
    import backend.media_processor as processor

    source = tmp_path / "long-legacy.avi"
    subprocess.run([
        FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=160x120:d=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-shortest", "-c:v", "mpeg4", "-c:a", "libmp3lame", str(source),
    ], check=True, timeout=30)

    monkeypatch.setattr(processor, "PARALLEL_THRESHOLD_SECONDS", 1)
    monkeypatch.setattr(processor, "PARALLEL_SEGMENT_SECONDS", 1)
    monkeypatch.setattr(processor, "PARALLEL_WORKERS", 2)

    parallel_calls = []
    original_parallel = processor._encode_parallel_segments

    async def tracked_parallel(*args, **kwargs):
        parallel_calls.append(args[4])
        return await original_parallel(*args, **kwargs)

    monkeypatch.setattr(processor, "_encode_parallel_segments", tracked_parallel)

    with source.open("rb") as media:
        mp3_res = client.post("/api/jobs/upload", files={"file": ("long-legacy.avi", media, "video/x-msvideo")}, data={"output": "mp3", "bitrate": "128"})
    assert mp3_res.status_code == 202
    mp3_job = wait_for_job(client, mp3_res.json()["id"])
    assert mp3_job["status"] == "completed", mp3_job.get("message")
    mp3_out = tmp_path / "parallel.mp3"
    mp3_out.write_bytes(client.get(f"/api/jobs/{mp3_job['id']}/download").content)
    mp3_info = json.loads(subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name", "-of", "json", str(mp3_out)], capture_output=True, check=True).stdout)
    assert float(mp3_info["format"]["duration"]) >= 2.5
    assert ("audio", "mp3") in {(s["codec_type"], s["codec_name"]) for s in mp3_info["streams"]}
    assert client.delete(f"/api/jobs/{mp3_job['id']}").status_code == 204

    with source.open("rb") as media:
        mp4_res = client.post("/api/jobs/upload", files={"file": ("long-legacy.avi", media, "video/x-msvideo")}, data={"output": "mp4", "quality": "compact"})
    assert mp4_res.status_code == 202
    mp4_job = wait_for_job(client, mp4_res.json()["id"])
    assert mp4_job["status"] == "completed", mp4_job.get("message")
    mp4_out = tmp_path / "parallel.mp4"
    mp4_out.write_bytes(client.get(f"/api/jobs/{mp4_job['id']}/download").content)
    mp4_info = json.loads(subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name", "-of", "json", str(mp4_out)], capture_output=True, check=True).stdout)
    assert float(mp4_info["format"]["duration"]) >= 2.5
    assert {("video", "h264"), ("audio", "aac")}.issubset({(s["codec_type"], s["codec_name"]) for s in mp4_info["streams"]})
    assert client.delete(f"/api/jobs/{mp4_job['id']}").status_code == 204

    assert parallel_calls == ["mp3", "mp4"]
    for job_id in (mp3_job["id"], mp4_job["id"]):
        assert not list(UPLOAD_DIR.glob(f"{job_id}.part*"))
        assert not list(UPLOAD_DIR.glob(f"{job_id}.concat.txt"))


def test_unreachable_direct_source_returns_actionable_failure(client, monkeypatch):
    from fastapi import HTTPException

    async def unavailable(url, destination, job_id):
        raise HTTPException(502, {"code": "source_unavailable", "message": "Server sumber menolak koneksi.", "next_step": "Gunakan URL publik lain atau unggah file."})

    monkeypatch.setattr("backend.main.fetch_direct_media", unavailable)
    response = client.post("/api/jobs/url", json={"url": "https://cdn.example.test/video.mp4", "output": "mp4"})
    assert response.status_code == 202
    job = wait_for_job(client, response.json()["id"])
    assert job["status"] == "failed"
    assert "menolak koneksi" in job["message"]


@pytest.mark.skipif(not media_tools_available(), reason="FFmpeg/FFprobe belum tersedia")
def test_invalid_file_is_rejected_by_probe_even_with_mp4_extension(client):
    response = client.post("/api/jobs/upload", files={"file": ("not-a-video.mp4", b"not a video", "video/mp4")}, data={"output": "mp4"})
    assert response.status_code == 202
    job = wait_for_job(client, response.json()["id"])
    assert job["status"] == "failed"
    assert "tidak terbaca" in job["message"] or "metadata" in job["message"]


def test_upload_size_limit_returns_413(client, monkeypatch):
    monkeypatch.setattr("backend.main.MAX_UPLOAD_BYTES", 3)
    response = client.post("/api/jobs/upload", files={"file": ("large.mp4", b"four", "video/mp4")}, data={"output": "mp4"})
    assert response.status_code == 413


@pytest.mark.skipif(not media_tools_available(), reason="FFmpeg/FFprobe belum tersedia")
def test_missing_ffmpeg_returns_failed_job(client, monkeypatch, tmp_path):
    import backend.media_processor as processor

    source = tmp_path / "sample.mp4"
    make_sample_video(source)
    monkeypatch.setattr(processor, "FFMPEG", str(tmp_path / "ffmpeg-missing.exe"))
    with source.open("rb") as media:
        response = client.post("/api/jobs/upload", files={"file": ("sample.mp4", media, "video/mp4")}, data={"output": "mp4"})
    assert response.status_code == 202
    job = wait_for_job(client, response.json()["id"])
    assert job["status"] == "failed"
    assert "FFmpeg tidak ditemukan" in job["message"]


def test_cancel_endpoint_marks_job_canceled(client, monkeypatch):
    import asyncio

    async def wait_forever(job_id, path):
        try:
            await asyncio.sleep(60)
        finally:
            path.unlink(missing_ok=True)

    monkeypatch.setattr("backend.job_manager.run_job", wait_forever)
    response = client.post("/api/jobs/upload", files={"file": ("cancel.mp4", b"fake", "video/mp4")}, data={"output": "mp4"})
    assert response.status_code == 202
    job_id = response.json()["id"]
    canceled = client.post(f"/api/jobs/{job_id}/cancel")
    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"




def test_jobs_are_private_per_visitor():
    from fastapi.testclient import TestClient
    from backend.job_manager import JOBS, OWNER, create_job
    from backend.main import app
    token = OWNER.set("a" * 32)
    job = create_job("rahasia.mp3", "mp3", 192)
    OWNER.reset(token)
    try:
        owner = TestClient(app, cookies={"zc_owner": "a" * 32})
        stranger = TestClient(app, cookies={"zc_owner": "b" * 32})
        assert owner.get(f"/api/jobs/{job['id']}").status_code == 200
        assert [item["id"] for item in owner.get("/api/jobs").json()] == [job["id"]]
        assert stranger.get(f"/api/jobs/{job['id']}").status_code == 404
        assert stranger.get("/api/jobs").json() == []
        assert stranger.get(f"/api/jobs/{job['id']}/download").status_code == 404
        assert stranger.post(f"/api/jobs/{job['id']}/cancel").status_code == 404
        assert stranger.delete(f"/api/jobs/{job['id']}").status_code == 404
        assert job["id"] in JOBS
    finally:
        JOBS.pop(job["id"], None)


def test_ads_txt_lists_the_publisher(client):
    response = client.get("/ads.txt")
    assert response.status_code == 200
    assert "pub-6898176272342462" in response.text and response.headers["content-type"].startswith("text/plain")


@pytest.mark.parametrize("path", ["/", "/mp4-ke-mp3", "/video-ke-musik", "/panduan-konversi", "/panduan-bitrate-mp3", "/faq", "/tentang", "/kebijakan-privasi", "/syarat-layanan"])
def test_content_pages_render_without_leftover_placeholders(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert "{{" not in response.text
    assert "google-adsense-account" in response.text
    if path in {"/kebijakan-privasi", "/syarat-layanan"}:
        assert "pagead2.googlesyndication.com" not in response.text
    else:
        assert "pagead2.googlesyndication.com" in response.text
    assert '<link rel="canonical"' in response.text


def test_seo_files_and_unknown_pages(client):
    assert "/kebijakan-privasi" in client.get("/sitemap.xml").text
    assert "Sitemap:" in client.get("/robots.txt").text
    assert client.get("/ads.txt").status_code == 200
    assert client.get("/tidak-ada").status_code == 404


@pytest.mark.skipif(not media_tools_available(), reason="FFmpeg/FFprobe belum tersedia")
def test_h264_with_non_aac_audio_copies_video_without_parallel_reencode(client, monkeypatch, tmp_path):
    import backend.media_processor as processor

    source = tmp_path / "h264-mp3.mkv"
    subprocess.run([
        FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=160x120:d=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-shortest", "-c:v", "libx264", "-c:a", "libmp3lame", str(source),
    ], check=True, timeout=30)

    monkeypatch.setattr(processor, "PARALLEL_THRESHOLD_SECONDS", 1)
    monkeypatch.setattr(processor, "PARALLEL_WORKERS", 2)

    async def fail_parallel(*args, **kwargs):
        raise AssertionError("_encode_parallel_segments tidak boleh dipanggil saat video sudah H.264")

    monkeypatch.setattr(processor, "_encode_parallel_segments", fail_parallel)

    with source.open("rb") as media:
        res = client.post("/api/jobs/upload", files={"file": ("h264-mp3.mkv", media, "video/x-matroska")}, data={"output": "mp4", "quality": "standard"})
    assert res.status_code == 202
    job = wait_for_job(client, res.json()["id"])
    assert job["status"] == "completed", job.get("message")
    out = tmp_path / "h264-copied.mp4"
    out.write_bytes(client.get(f"/api/jobs/{job['id']}/download").content)
    info = json.loads(subprocess.run([FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,codec_name", "-of", "json", str(out)], capture_output=True, check=True).stdout)
    codecs = {(s["codec_type"], s["codec_name"]) for s in info["streams"]}
    assert {("video", "h264"), ("audio", "aac")}.issubset(codecs)
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 204


def test_multi_hour_limits_and_home_has_no_architecture_section(client):
    from backend.config import MAX_MEDIA_SECONDS, MAX_PROCESS_SECONDS, MAX_REMOTE_BYTES, MAX_UPLOAD_BYTES

    assert MAX_MEDIA_SECONDS >= 2 * 3600
    assert MAX_PROCESS_SECONDS >= 3600
    assert MAX_UPLOAD_BYTES >= 2048 * 1024 * 1024
    assert MAX_REMOTE_BYTES >= 2048 * 1024 * 1024

    html = client.get("/").text
    assert "Cara Penggunaan" in html
    assert "Maksimal 2 GB" in html
    for forbidden in ("sys-card", "sys-illus", "Smart Media Analyzer", "High-Speed Engine", "Turbo Processing", "Private Session Lock"):
        assert forbidden not in html


def test_resolve_stream_plan_selects_direct_mux_and_mp3(monkeypatch):
    import asyncio
    from backend import ytdlp

    async def fake_fetch_youtube(url: str) -> dict:
        return {
            "id": "abc12345678",
            "title": "Demo Video",
            "uploader": "Creator",
            "duration": 180,
            "thumbnail": "https://img.example.test/thumb.jpg",
            "http_headers": {"User-Agent": "TestUA"},
            "formats": [
                {"format_id": "18", "url": "https://cdn.example.test/360.mp4", "ext": "mp4", "protocol": "https", "height": 360, "vcodec": "avc1.42001E", "acodec": "mp4a.40.2", "filesize": 1000},
                {"format_id": "136", "url": "https://cdn.example.test/720v.mp4", "ext": "mp4", "protocol": "https", "height": 720, "vcodec": "avc1.4d401f", "acodec": "none", "filesize": 4000},
                {"format_id": "140", "url": "https://cdn.example.test/audio.m4a", "ext": "m4a", "protocol": "https", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 128, "filesize": 500},
            ],
        }

    monkeypatch.setattr(ytdlp, "fetch_info", fake_fetch_youtube)
    mux_plan = asyncio.run(ytdlp.resolve_stream_plan("https://www.youtube.com/watch?v=abc12345678", "mp4", "standard", 192))
    assert mux_plan["mode"] == "ffmpeg_mux"
    assert mux_plan["video_copy"] is True
    assert mux_plan["audio_copy"] is True
    assert mux_plan["video_url"] == "https://cdn.example.test/720v.mp4"
    assert mux_plan["audio_url"] == "https://cdn.example.test/audio.m4a"
    assert mux_plan["output_name"] == "Demo Video.mp4"

    mp3_plan = asyncio.run(ytdlp.resolve_stream_plan("https://www.youtube.com/watch?v=abc12345678", "mp3", "standard", 192))
    assert mp3_plan["mode"] == "ffmpeg_mp3"
    assert mp3_plan["input_url"] == "https://cdn.example.test/audio.m4a"
    assert mp3_plan["output_name"] == "Demo Video.mp3"

    async def fake_fetch_progressive(url: str) -> dict:
        return {
            "id": "999",
            "title": "TikTok Clip",
            "duration": 30,
            "formats": [
                {"format_id": "hd", "url": "https://cdn.example.test/tiktok.mp4", "ext": "mp4", "protocol": "https", "height": 1080, "vcodec": "h264", "acodec": "aac", "filesize": 2500},
            ],
        }

    monkeypatch.setattr(ytdlp, "fetch_info", fake_fetch_progressive)
    prog_plan = asyncio.run(ytdlp.resolve_stream_plan("https://www.tiktok.com/@user/video/999", "mp4", "high", 192))
    assert prog_plan["mode"] == "direct_proxy"
    assert prog_plan["direct_url"] == "https://cdn.example.test/tiktok.mp4"


@pytest.mark.skipif(not media_tools_available(), reason="FFmpeg/FFprobe belum tersedia")
def test_quick_media_and_ffmpeg_mp3_stream(client, monkeypatch, tmp_path):
    source = tmp_path / "quick-source.mp4"
    make_sample_video(source)

    async def fake_plan(url: str, kind: str, quality: str = "standard", bitrate: int = 192) -> dict:
        return {
            "mode": "ffmpeg_mp3",
            "input_url": str(source),
            "headers": {},
            "bitrate": bitrate,
            "output_name": "Quick Lagu.mp3",
            "media_type": "audio/mpeg",
            "filesize": None,
            "title": "Quick Lagu",
            "author": "Artis",
            "duration": 1.0,
            "thumbnail": None,
        }

    monkeypatch.setattr("backend.main.YT_DLP_ENABLED", True)
    monkeypatch.setattr("backend.ytdlp.resolve_stream_plan", fake_plan)

    res = client.post("/api/media/quick", json={"url": "https://www.youtube.com/watch?v=abcdefghijk", "output": "mp3", "bitrate": 128})
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["status"] == "ready"
    assert payload["download_url"].startswith("/api/stream/")
    assert payload["output_name"] == "Quick Lagu.mp3"

    stream = client.get(payload["download_url"])
    assert stream.status_code == 200
    assert "attachment" in stream.headers.get("content-disposition", "").lower()
    assert stream.headers.get("content-type", "").startswith("audio/mpeg")
    out = tmp_path / "streamed.mp3"
    out.write_bytes(stream.content)
    info = json.loads(subprocess.run([FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,codec_name", "-of", "json", str(out)], capture_output=True, check=True).stdout)
    assert ("audio", "mp3") in {(s["codec_type"], s["codec_name"]) for s in info["streams"]}
    assert client.get("/api/stream/nonexistenttoken").status_code == 404
