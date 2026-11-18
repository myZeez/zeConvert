import asyncio
import json
import re
import sys
import time
import uuid
from pathlib import Path

import yt_dlp

from .config import FFMPEG, MAX_MEDIA_SECONDS, MAX_REMOTE_BYTES, STORAGE_DIR, UPLOAD_DIR, YT_DLP_TIMEOUT_SECONDS

# Run without user config, cookies, or proxies; playlists are never expanded.
CACHE_DIR = STORAGE_DIR / "yt-dlp-cache"
BASE_ARGS = [sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-playlist", "--no-warnings", "--cache-dir", str(CACHE_DIR), "--js-runtimes", "node"]
HEIGHT_LIMIT = {"high": 1080, "standard": 720, "compact": 480}
_INFO_CACHE_TTL = 600
_INFO_CACHE: dict[str, tuple[float, dict]] = {}


def _ffmpeg_args() -> list[str]:
    path = Path(FFMPEG)
    return ["--ffmpeg-location", str(path.parent)] if path.is_file() else []


def _clean_error_text(raw: str) -> str:
    lines = raw.strip().splitlines()
    last = next((line for line in reversed(lines) if "ERROR:" in line or line.startswith("ERROR")), raw)
    last = re.sub(r"^(?:.*?\b)?ERROR:\s*(\[[^\]]+\]\s*[\w-]+:\s*)?", "", last)
    return last.strip()[:300] or "yt-dlp gagal membaca video ini."


def _clean_error(stderr: bytes) -> str:
    return _clean_error_text(stderr.decode("utf-8", "ignore"))


def _extract_info_sync(url: str) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "ignoreconfig": True,
        "extract_flat": False,
        "cachedir": str(CACHE_DIR),
        "socket_timeout": 20,
        "js_runtimes": {"node": {}},
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return ydl.sanitize_info(info) if info else {}


async def fetch_info(url: str) -> dict:
    now = time.time()
    cached = _INFO_CACHE.get(url)
    if cached and now - cached[0] < _INFO_CACHE_TTL:
        return cached[1]
    try:
        data = await asyncio.wait_for(asyncio.to_thread(_extract_info_sync, url), timeout=YT_DLP_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        raise RuntimeError("Pengambilan info video melewati batas waktu.")
    except yt_dlp.utils.DownloadError as error:
        raise RuntimeError(_clean_error_text(str(error)))
    if not isinstance(data, dict) or not data:
        raise RuntimeError("Respons yt-dlp tidak dapat dibaca.")
    if len(_INFO_CACHE) >= 64:
        _INFO_CACHE.clear()
    _INFO_CACHE[url] = (time.time(), data)
    return data


def _is_direct_http(fmt: dict) -> bool:
    url = str(fmt.get("url") or "")
    protocol = fmt.get("protocol")
    return url.startswith(("https://", "http://")) and protocol in {"https", "http", None}


def _headers_for(fmt: dict, info: dict) -> dict[str, str]:
    headers = {str(k): str(v) for k, v in (info.get("http_headers") or {}).items() if v is not None}
    headers.update({str(k): str(v) for k, v in (fmt.get("http_headers") or {}).items() if v is not None})
    if fmt.get("cookies"):
        headers["Cookie"] = str(fmt["cookies"])
    return headers


def safe_filename(title: str, kind: str) -> str:
    stem = re.sub(r"[^\w .()-]", "_", title or "media", flags=re.UNICODE).strip(" .")[:100] or "media"
    return f"{stem}.{kind}"


def _fmt_filesize(fmt: dict) -> int | None:
    raw = fmt.get("filesize") or fmt.get("filesize_approx")
    try:
        value = int(raw)
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def _pick_by_height(candidates: list[dict], target_h: int, prefer_mp4_h264: bool = True) -> dict:
    def rank(fmt: dict) -> tuple:
        height = int(fmt.get("height") or 0)
        within_target = 1 if (height == 0 or height <= target_h) else 0
        height_score = height if within_target else -height
        vcodec = str(fmt.get("vcodec") or "").lower()
        is_h264 = 1 if (not prefer_mp4_h264 or vcodec.startswith(("avc1", "h264")) or vcodec in {"", "none"}) else 0
        is_mp4 = 1 if (fmt.get("ext") in {"mp4", None}) else 0
        size = _fmt_filesize(fmt)
        within_bytes = 1 if (size is None or size <= MAX_REMOTE_BYTES) else 0
        return (within_bytes, within_target, height_score, is_h264, is_mp4, float(fmt.get("tbr") or 0))

    return max(candidates, key=rank)


async def resolve_stream_plan(url: str, kind: str, quality: str = "standard", bitrate: int = 192) -> dict:
    """Resolve direct CDN stream URLs from memory without downloading media to disk."""
    info = await fetch_info(url)
    duration = float(info.get("duration") or 0)
    if duration > MAX_MEDIA_SECONDS:
        raise RuntimeError(f"Durasi video melebihi batas {MAX_MEDIA_SECONDS // 60} menit.")

    title = str(info.get("title") or info.get("description") or "Media")[:180]
    author = info.get("uploader") or info.get("channel")
    thumbnail = info.get("thumbnail")
    output_name = safe_filename(title, kind)
    base_meta = {
        "title": title,
        "author": author,
        "duration": duration or None,
        "thumbnail": thumbnail,
        "output_name": output_name,
    }

    formats = [f for f in (info.get("formats") or []) if isinstance(f, dict) and _is_direct_http(f)]
    if not formats and _is_direct_http(info):
        formats = [info]
    if not formats:
        raise RuntimeError("Stream langsung tidak tersedia untuk video ini.")

    if kind == "mp3":
        audio_only = [f for f in formats if f.get("vcodec") == "none" and f.get("acodec") not in {None, "none"}]
        candidates = audio_only or [f for f in formats if f.get("acodec") != "none"]
        if not candidates:
            raise RuntimeError("Stream audio langsung tidak tersedia untuk video ini.")

        def audio_rank(fmt: dict) -> tuple:
            size = _fmt_filesize(fmt)
            within_bytes = 1 if (size is None or size <= MAX_REMOTE_BYTES) else 0
            is_audio_only = 1 if fmt.get("vcodec") == "none" else 0
            acodec = str(fmt.get("acodec") or "").lower()
            is_aac = 1 if (fmt.get("ext") == "m4a" or acodec.startswith(("mp4a", "aac"))) else 0
            abr = float(fmt.get("abr") or fmt.get("tbr") or 0)
            sweet_spot = 1 if (0 < abr <= 192) else 0
            return (within_bytes, is_audio_only, is_aac, sweet_spot, abr)

        picked = max(candidates, key=audio_rank)
        return {
            **base_meta,
            "mode": "ffmpeg_mp3",
            "input_url": picked["url"],
            "headers": _headers_for(picked, info),
            "bitrate": int(bitrate),
            "media_type": "audio/mpeg",
            "filesize": None,
        }

    target_h = HEIGHT_LIMIT.get(quality, 720)
    progressive = [
        f for f in formats
        if f.get("vcodec") != "none"
        and f.get("acodec") != "none"
        and (
            f.get("ext") in {"mp4", None}
            or str(f.get("vcodec") or "").lower().startswith(("avc1", "h264"))
        )
    ]
    video_h264 = [
        f for f in formats
        if str(f.get("vcodec") or "").lower().startswith(("avc1", "h264"))
        and f.get("acodec") in {None, "none"}
    ]
    video_any = [
        f for f in formats
        if f.get("vcodec") not in {None, "none"}
        and f.get("acodec") in {None, "none"}
    ]
    audio_only = [f for f in formats if f.get("vcodec") == "none" and f.get("acodec") not in {None, "none"}]

    video_pool = video_h264 or video_any
    max_video_height = max((int(f.get("height") or 0) for f in [*progressive, *video_pool]), default=0)
    best_prog = _pick_by_height(progressive, target_h) if progressive else None
    prog_h = int(best_prog.get("height") or 0) if best_prog else 0

    if best_prog and (prog_h >= min(target_h, max_video_height) or not (video_pool and audio_only)):
        return {
            **base_meta,
            "mode": "direct_proxy",
            "direct_url": best_prog["url"],
            "headers": _headers_for(best_prog, info),
            "filesize": _fmt_filesize(best_prog),
            "media_type": "video/mp4",
        }

    if video_pool and audio_only:
        best_video = _pick_by_height(video_pool, target_h)
        best_audio = max(
            audio_only,
            key=lambda f: (
                1 if (_fmt_filesize(f) is None or (_fmt_filesize(f) or 0) <= MAX_REMOTE_BYTES) else 0,
                1 if (f.get("ext") == "m4a" or str(f.get("acodec") or "").lower().startswith(("mp4a", "aac"))) else 0,
                float(f.get("abr") or f.get("tbr") or 0),
            ),
        )
        v_size = _fmt_filesize(best_video)
        a_size = _fmt_filesize(best_audio)
        return {
            **base_meta,
            "mode": "ffmpeg_mux",
            "video_url": best_video["url"],
            "audio_url": best_audio["url"],
            "video_headers": _headers_for(best_video, info),
            "audio_headers": _headers_for(best_audio, info),
            "video_copy": str(best_video.get("vcodec") or "").lower().startswith(("avc1", "h264")),
            "audio_copy": str(best_audio.get("acodec") or "").lower().startswith(("mp4a", "aac")),
            "filesize": (v_size + a_size) if (v_size and a_size) else None,
            "media_type": "video/mp4",
        }

    if progressive:
        best_prog = _pick_by_height(progressive, target_h)
        return {
            **base_meta,
            "mode": "direct_proxy",
            "direct_url": best_prog["url"],
            "headers": _headers_for(best_prog, info),
            "filesize": _fmt_filesize(best_prog),
            "media_type": "video/mp4",
        }

    raise RuntimeError("Stream langsung tidak tersedia untuk video ini.")


async def _exec_download(target_args: list[str], prefix: str, fmt: str, sort_args: list[str], merge_args: list[str], on_progress, on_title) -> Path:
    template = str(UPLOAD_DIR / f"{prefix}.%(ext)s")
    args = [*BASE_ARGS, "-f", fmt, *sort_args, *merge_args, "--concurrent-fragments", "8",
            "--retries", "10", "--fragment-retries", "10", "--retry-sleep", "fragment:exp=1:5",
            "--socket-timeout", "30", "--newline",
            "--no-simulate", "--progress", "--print", "before_dl:TITLE %(title)s",
            "--max-filesize", str(MAX_REMOTE_BYTES), "--match-filter", f"duration<=?{MAX_MEDIA_SECONDS}",
            "--progress-template", "download:PCT %(progress._percent_str)s", "-o", template, *_ffmpeg_args(), *target_args]
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    skip_reason = None

    async def read_progress():
        nonlocal skip_reason
        while line := await proc.stdout.readline():
            line_text = line.decode("utf-8", "ignore").strip()
            if line_text.startswith("TITLE "):
                if on_title:
                    on_title(line_text[6:].strip())
                continue
            if "does not pass filter" in line_text:
                skip_reason = f"Durasi video melebihi batas {MAX_MEDIA_SECONDS // 60} menit."
                continue
            if "File is larger than max-filesize" in line_text:
                skip_reason = f"Ukuran video melebihi batas {MAX_REMOTE_BYTES // (1024 * 1024)} MB."
                continue
            match = re.search(r"PCT\s+([\d.]+)%", line_text)
            if match:
                on_progress(min(99, int(float(match.group(1)))))

    stderr_task = asyncio.create_task(proc.stderr.read())
    progress_task = asyncio.create_task(read_progress())
    try:
        await proc.wait()
        await progress_task
        stderr = await stderr_task
    except BaseException:
        proc.kill()
        await proc.wait()
        progress_task.cancel()
        stderr_task.cancel()
        _remove_parts(prefix)
        raise
    if proc.returncode != 0:
        _remove_parts(prefix)
        raise RuntimeError(_clean_error(stderr))
    files = [p for p in UPLOAD_DIR.glob(f"{prefix}.*") if p.suffix not in {".part", ".ytdl"} and not p.name.endswith(".info.json")]
    if not files:
        stderr_text = stderr.decode("utf-8", "ignore")
        if not skip_reason and "does not pass filter" in stderr_text:
            skip_reason = f"Durasi video melebihi batas {MAX_MEDIA_SECONDS // 60} menit."
        elif not skip_reason and "File is larger than max-filesize" in stderr_text:
            skip_reason = f"Ukuran video melebihi batas {MAX_REMOTE_BYTES // (1024 * 1024)} MB."
        _remove_parts(prefix)
        raise RuntimeError(skip_reason or "Video tidak berhasil diunduh (mungkin melebihi batas ukuran atau durasi).")
    return max(files, key=lambda p: p.stat().st_size)


async def download(url: str, kind: str, quality: str, on_progress, on_title=None) -> Path:
    """Download the best matching streams into UPLOAD_DIR and return the file path."""
    prefix = uuid.uuid4().hex
    if kind == "mp3":
        fmt = f"ba[ext=m4a][filesize<=?{MAX_REMOTE_BYTES}]/ba[filesize<=?{MAX_REMOTE_BYTES}]/ba[ext=m4a]/ba/b"
        sort_args = ["-S", "abr:160,ext:m4a"]
        merge_args = []
    else:
        height = HEIGHT_LIMIT.get(quality, 720)
        # Prefer H.264 + AAC so FFmpeg can stream-copy instead of re-encoding; res handles both landscape and portrait.
        fmt = (
            f"bv*[vcodec^=avc1][filesize<=?{MAX_REMOTE_BYTES}]+ba[acodec^=mp4a]"
            f"/bv*[vcodec^=avc1][filesize<=?{MAX_REMOTE_BYTES}]+ba"
            f"/bv*[filesize<=?{MAX_REMOTE_BYTES}]+ba/b[filesize<=?{MAX_REMOTE_BYTES}]/bv*+ba/b"
        )
        sort_args = ["-S", f"vcodec:h264,res:{height},acodec:aac,ext:mp4:m4a"]
        merge_args = ["--merge-output-format", "mp4"]

    cached = _INFO_CACHE.get(url)
    if cached and time.time() - cached[0] < _INFO_CACHE_TTL and isinstance(cached[1], dict) and (cached[1].get("formats") or cached[1].get("url")):
        info = cached[1]
        if on_title and info.get("title"):
            on_title(str(info["title"]))
        info_path = UPLOAD_DIR / f"{prefix}.info.json"
        info_path.write_text(json.dumps(info), encoding="utf-8")
        try:
            return await _exec_download(["--load-info-json", str(info_path)], prefix, fmt, sort_args, merge_args, on_progress, on_title)
        except RuntimeError:
            _INFO_CACHE.pop(url, None)
            _remove_parts(prefix)
        finally:
            info_path.unlink(missing_ok=True)

    return await _exec_download([url], prefix, fmt, sort_args, merge_args, on_progress, on_title)


def _remove_parts(prefix: str) -> None:
    for item in UPLOAD_DIR.glob(f"{prefix}.*"):
        item.unlink(missing_ok=True)
