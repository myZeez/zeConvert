import asyncio
import os
import re
import ipaddress
import logging
import socket
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

import aiohttp
from aiohttp.abc import AbstractResolver
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import FFMPEG, FRONTEND_DIR, MAX_ACTIVE_JOBS, MAX_ACTIVE_PREVIEWS, MAX_REMOTE_BYTES, MAX_UPLOAD_BYTES, OUTPUT_DIR, PREVIEW_TTL_SECONDS, UPLOAD_DIR, YT_DLP_ENABLED
from .job_manager import JOBS, OWNER, TASKS, cancel_job, cleanup_expired, create_job, delete_job, public_job, run_job, start_job, update_job
from .media_processor import probe
from .providers import classify_url
from .providers.registry import get_platform_provider
from .providers.youtube import YouTubeProvider
from . import pages, ytdlp


class UrlJobRequest(BaseModel):
    url: str | None = Field(default=None, min_length=8, max_length=4096)
    preview_id: str | None = Field(default=None, min_length=32, max_length=32)
    output: str = "mp4"
    bitrate: int = 192
    quality: str = "standard"


class MediaResolveRequest(BaseModel):
    url: str = Field(default="", max_length=4096)


class MediaInfoRequest(BaseModel):
    url: str = Field(default="", min_length=8, max_length=4096)


class PublicAddressResolver(AbstractResolver):
    async def resolve(self, host, port=0, family=socket.AF_UNSPEC):
        try:
            literal = ipaddress.ip_address(host)
            addresses = [(socket.AF_INET6 if literal.version == 6 else socket.AF_INET, str(literal))]
        except ValueError:
            try:
                results = await asyncio.get_running_loop().getaddrinfo(host, port, family=family, type=socket.SOCK_STREAM)
            except OSError:
                raise OSError("Host tidak dapat di-resolve.")
            addresses = list(dict.fromkeys((item[0], item[4][0]) for item in results))
        if not addresses or any(not ipaddress.ip_address(address).is_global for _, address in addresses):
            raise OSError("Alamat tujuan bukan alamat publik yang diizinkan.")
        return [{"hostname": host, "host": address, "port": port, "family": fam, "proto": 0, "flags": 0} for fam, address in addresses]

    async def close(self):
        return None


def validate_public_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(400, "Gunakan URL HTTPS langsung ke file media, tanpa informasi login di URL.")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "metadata.google.internal"} or host.endswith((".localhost", ".local", ".internal")):
        raise HTTPException(400, "Host ini tidak diizinkan.")
    try:
        literal = ipaddress.ip_address(host)
        if not literal.is_global:
            raise HTTPException(400, "Alamat IP privat atau khusus tidak diizinkan.")
    except ValueError:
        pass
    return value


PREVIEWS: dict[str, dict] = {}
STREAM_TOKENS: dict[str, dict] = {}


async def fetch_direct_media(url: str, destination: Path, job_id: str | None) -> tuple[str, int]:
    current = validate_public_url(url)
    timeout = aiohttp.ClientTimeout(total=1800, connect=20, sock_read=60)
    connector = aiohttp.TCPConnector(resolver=PublicAddressResolver(), use_dns_cache=False)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout, trust_env=False, headers={"User-Agent": "PutarVideo/1.0"}) as session:
        for redirect_count in range(6):
            current = validate_public_url(current)
            try:
                response = await session.get(current, allow_redirects=False)
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
                raise HTTPException(502, {"code": "source_unavailable", "message": "Sumber media tidak dapat dijangkau atau host menolak koneksi.", "next_step": "Pastikan URL publik, aktif, tidak membutuhkan login, dan memakai HTTPS."})
            async with response:
                if response.status in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location")
                    if not location or redirect_count == 5:
                        raise HTTPException(400, "Pengalihan URL tidak valid atau terlalu banyak.")
                    current = urljoin(current, location)
                    continue
                if response.status != 200:
                    raise HTTPException(502, {"code": "source_unavailable", "message": f"Sumber media menjawab HTTP {response.status}.", "next_step": "Periksa apakah tautan masih aktif dan file dapat diakses tanpa login."})
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                if not (content_type.startswith(("video/", "audio/")) or content_type == "application/octet-stream"):
                    raise HTTPException(415, {"code": "not_media_file", "message": f"URL mengembalikan {content_type or 'tipe konten tidak diketahui'}, bukan file audio/video.", "next_step": "Gunakan URL file media langsung atau unggah file hasil ekspor platform."})
                length = response.content_length
                if length is not None and length > MAX_REMOTE_BYTES:
                    raise HTTPException(413, f"Berkas sumber melebihi batas ukuran {MAX_REMOTE_BYTES // (1024 * 1024)} MB.")
                total = 0
                expected = response.content_length
                if job_id:
                    update_job(job_id, status="processing", stage="Mengunduh media", progress=0 if expected else None, message="Backend sedang mengunduh berkas media langsung dari URL HTTPS.")
                try:
                    with destination.open("wb") as output:
                        async for chunk in response.content.iter_chunked(1024 * 256):
                            total += len(chunk)
                            if total > MAX_REMOTE_BYTES:
                                raise HTTPException(413, f"Berkas sumber melebihi batas ukuran {MAX_REMOTE_BYTES // (1024 * 1024)} MB.")
                            output.write(chunk)
                            if expected and job_id:
                                update_job(job_id, progress=min(99, int(total / expected * 100)))
                except Exception:
                    destination.unlink(missing_ok=True)
                    raise
                if total == 0:
                    raise HTTPException(400, "Berkas sumber kosong.")
                return content_type, total
    raise HTTPException(400, "Pengalihan URL tidak valid.")


async def inspect_direct_media(url: str) -> dict:
    """Read response headers only; this endpoint never downloads the media body."""
    current = validate_public_url(url)
    timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=10)
    connector = aiohttp.TCPConnector(resolver=PublicAddressResolver(), use_dns_cache=False)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout, trust_env=False, headers={"User-Agent": "PutarVideo/1.0"}) as session:
        method = "HEAD"
        for redirect_count in range(6):
            current = validate_public_url(current)
            try:
                request_headers = {"Range": "bytes=0-0"} if method == "GET" else None
                async with session.request(method, current, headers=request_headers, allow_redirects=False) as response:
                    if method == "HEAD" and response.status in {403, 405, 501}:
                        method = "GET"
                        continue
                    if response.status in (301, 302, 303, 307, 308):
                        location = response.headers.get("Location")
                        if not location or redirect_count == 5:
                            raise HTTPException(400, "Pengalihan URL tidak valid atau terlalu banyak.")
                        current = urljoin(current, location)
                        continue
                    if response.status in {401, 403}:
                        raise HTTPException(403, {"code": "source_requires_auth", "message": "Sumber meminta autentikasi atau menolak akses tanpa izin.", "next_step": "Gunakan file yang kamu miliki atau unggah hasil ekspor resmi; aplikasi tidak meminta atau melewati kredensial."})
                    if response.status >= 400:
                        raise HTTPException(502, {"code": "source_unavailable", "message": f"Sumber media menjawab HTTP {response.status}.", "next_step": "Periksa apakah URL publik dan masih aktif."})
                    mime = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                    if not (mime.startswith(("video/", "audio/")) or mime == "application/octet-stream"):
                        raise HTTPException(415, {"code": "not_media_file", "message": f"URL mengembalikan {mime or 'tipe yang tidak diketahui'}, bukan file audio/video.", "next_step": "Gunakan URL file media langsung atau unggah file hasil ekspor."})
                    raw_size = response.headers.get("Content-Length")
                    size = int(raw_size) if raw_size and raw_size.isdigit() else None
                    if method == "GET":
                        raw_range = response.headers.get("Content-Range", "")
                        try:
                            size = int(raw_range.rsplit("/", 1)[1])
                        except (IndexError, ValueError):
                            size = None
                    if size is not None and size > MAX_REMOTE_BYTES:
                        raise HTTPException(413, f"Berkas sumber melebihi batas ukuran {MAX_REMOTE_BYTES // (1024 * 1024)} MB.")
                    if method == "GET":
                        await response.content.read(1)
                    return {"status": "accessible", "mime_type": mime, "size": size,
                            "filename": Path(urlparse(current).path).name or None,
                            "duration": None, "resolution": None, "video_codec": None, "audio_codec": None,
                            "formats": [{"container": mime, "size": size, "quality": "Tidak diketahui dari header URL"}],
                            "metadata_available": False,
                            "message": "URL mengirim tipe media yang sesuai. Durasi, resolusi, dan codec baru tersedia setelah file dibaca dengan FFprobe."}
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
                raise HTTPException(502, {"code": "source_unavailable", "message": "Sumber media tidak dapat dijangkau.", "next_step": "Pastikan URL publik, aktif, dan dapat diakses server tanpa login."})
    raise HTTPException(400, "Pengalihan URL tidak valid.")


async def cleanup_loop():
    while True:
        await asyncio.sleep(300)
        await cleanup_expired()
        now = time.time()
        for preview_id, preview in list(PREVIEWS.items()):
            if preview["expires_at"] <= now:
                PREVIEWS.pop(preview_id, None)
                Path(preview["path"]).unlink(missing_ok=True)
        for token, stream in list(STREAM_TOKENS.items()):
            if stream["expires_at"] <= now:
                STREAM_TOKENS.pop(token, None)


@asynccontextmanager
async def lifespan(app):
    cleanup_task = asyncio.create_task(cleanup_loop())
    yield
    cleanup_task.cancel()


app = FastAPI(title="Putar Video Media API", version="1.0.0", lifespan=lifespan)
class NoCacheStatic(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/static", NoCacheStatic(directory=FRONTEND_DIR), name="static")
logger = logging.getLogger("putarvideo")


def ensure_job_capacity():
    active = sum(job["status"] in {"queued", "processing"} for job in JOBS.values())
    if active >= MAX_ACTIVE_JOBS:
        raise HTTPException(429, "Antrean penuh. Coba lagi setelah pekerjaan yang sedang berjalan selesai.")


JOBS_PER_MINUTE = int(os.getenv("JOBS_PER_MINUTE", "0"))
_job_hits: dict[str, list[float]] = {}


@app.middleware("http")
async def limit_job_creation(request, call_next):
    """Batasi pembuatan pekerjaan per IP (0 = nonaktif). IP asli datang dari header proxy."""
    if JOBS_PER_MINUTE and request.method == "POST" and request.url.path.startswith("/api/jobs/") and not request.url.path.endswith("/cancel"):
        ip = request.client.host if request.client else "?"
        now = time.time()
        hits = [t for t in _job_hits.get(ip, []) if now - t < 60]
        if len(hits) >= JOBS_PER_MINUTE:
            _job_hits[ip] = hits
            return JSONResponse({"detail": "Terlalu banyak permintaan. Coba lagi sebentar."}, status_code=429)
        hits.append(now)
        _job_hits[ip] = hits
    return await call_next(request)


@app.middleware("http")
async def owner_cookie(request: Request, call_next):
    """Setiap pengunjung diberi ID acak (cookie). Pekerjaan hanya bisa diakses pemiliknya."""
    owner = request.cookies.get("zc_owner")
    is_new = not (owner and re.fullmatch(r"[0-9a-f]{32}", owner))
    if is_new:
        owner = uuid.uuid4().hex
    token = OWNER.set(owner)
    try:
        response = await call_next(request)
    finally:
        OWNER.reset(token)
    if is_new:
        secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        response.set_cookie("zc_owner", owner, httponly=True, samesite="lax", secure=secure, max_age=86400)
    return response


def owned_job(job_id: str) -> dict | None:
    job = JOBS.get(job_id)
    return job if job and job.get("_owner") == OWNER.get() else None


@app.get("/")
async def home():
    return HTMLResponse(pages.render_home(""), headers={"Cache-Control": "no-cache"})


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap_xml():
    return Response(pages.sitemap(), media_type="application/xml")


@app.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    return PlainTextResponse(pages.robots())



@app.get("/ads.txt", include_in_schema=False)
async def ads_txt():
    return PlainTextResponse("google.com, pub-6898176272342462, DIRECT, f08c47fec0942fa0\n", headers={"Cache-Control": "no-cache"})


@app.get("/api/health")
async def health():
    import shutil
    from .config import FFMPEG, FFPROBE
    return {"status": "ok", "ffmpeg_available": bool(shutil.which(FFMPEG) or Path(FFMPEG).is_file()), "ffprobe_available": bool(shutil.which(FFPROBE) or Path(FFPROBE).is_file())}


@app.post("/api/media/classify")
async def classify_media(request: MediaResolveRequest):
    """Classify a URL locally. This never claims that a file can be downloaded."""
    return public_resolution(classify_url(request.url).as_dict())


async def inspect_platform_source(url: str) -> dict | None:
    provider = get_platform_provider(url)
    if not provider:
        return None
    result = await provider.inspect(url)
    source_url = result.get("_media_url")
    if not source_url:
        return result
    try:
        source_info = await inspect_direct_media(source_url)
    except HTTPException as error:
        detail = error.detail if isinstance(error.detail, dict) else {"message": str(error.detail)}
        result.update({"status": detail.get("code", "source_unavailable"), "can_process": False,
                       "media_access": "official_api_url_unavailable", "_media_url": None,
                       "message": detail.get("message", "Provider resmi memberi URL sumber, tetapi server belum dapat mengakses file media."),
                       "next_step": detail.get("next_step", "Periksa izin provider atau unggah file hasil ekspor yang kamu miliki.")})
        return result
    result.update({"can_process": True, "media_access": "authorized_api_source_verified",
                   "status": "media_available", "mime_type": source_info["mime_type"],
                   "size": source_info["size"], "formats": source_info["formats"],
                   "message": "Provider resmi mengembalikan URL sumber dan backend memverifikasi tipe media serta aksesnya.",
                   "next_step": "Sumber dapat dikirim ke proses MP4 atau MP3."})
    return result


def public_resolution(result: dict) -> dict:
    """Remove internal provider URLs and make the verification boundary explicit."""
    result = dict(result)
    result.pop("_media_url", None)
    status = result.get("status", "unknown")
    can_process = bool(result.get("can_process"))
    header_verified = status in {"accessible", "media_available"}
    result["source"] = {
        "kind": "platform_api" if result.get("source_type") == "platform_page" else "direct_url",
        "access": "candidate" if can_process else "unavailable",
        "verification": "headers_verified" if header_verified else "not_verified",
        "reference": "server_managed" if can_process else None,
    }
    if can_process:
        result["message"] = result.get("message") or "Sumber dapat diajukan ke job. Backend akan mengunduh seluruh file dan memeriksanya dengan FFprobe sebelum FFmpeg dimulai."
    return result


async def build_media_inspection(url: str) -> dict:
    """Inspect public metadata and the *candidate* media source without exposing provider URLs."""
    resolution = classify_url(url)
    result = resolution.as_dict()
    result.update({"metadata_available": False, "title": None, "thumbnail": None, "duration": None,
                  "format": None, "resolution": None, "video_codec": None, "audio_codec": None,
                  "size": None, "formats": []})
    platform_info = await inspect_platform_source(url)
    if platform_info is not None:
        return public_resolution(platform_info)
    if not resolution.can_process:
        return public_resolution(result)
    try:
        result.update(await inspect_direct_media(url))
        result["provider"] = resolution.provider
        result["source_type"] = resolution.source_type
        result["can_process"] = True
    except HTTPException as error:
        if isinstance(error.detail, dict):
            result.update(error.detail)
            result["status"] = error.detail.get("code", "source_unavailable")
        else:
            result.update({"status": "source_unavailable", "message": str(error.detail)})
        result["can_process"] = False
    return public_resolution(result)


@app.post("/api/media/inspect")
@app.post("/api/media/info", include_in_schema=False)
async def media_info(request: MediaInfoRequest):
    return await build_media_inspection(request.url)


@app.post("/api/media/resolve")
async def resolve_media(request: MediaResolveRequest):
    """Resolve a source candidate only after provider/header inspection has completed."""
    return await build_media_inspection(request.url)


def _content_disposition(filename: str) -> str:
    clean_ascii = re.sub(r"[^A-Za-z0-9 ._()\-]", "_", filename or "media")
    return f'attachment; filename="{clean_ascii}"; filename*=UTF-8\'\'{quote(filename or "media")}'


def _ffmpeg_header_args(headers: dict[str, str] | None, input_url: str = "") -> list[str]:
    if input_url and not input_url.startswith(("http://", "https://")):
        return []
    args = ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]
    pairs = [f"{k}: {v}" for k, v in (headers or {}).items() if v and "\r" not in str(v) and "\n" not in str(v)]
    if pairs:
        args.extend(["-headers", "\r\n".join(pairs) + "\r\n"])
    return args


def _purge_expired_streams() -> None:
    now = time.time()
    for token, item in list(STREAM_TOKENS.items()):
        if item["expires_at"] <= now:
            STREAM_TOKENS.pop(token, None)


@app.post("/api/media/quick")
async def quick_media(request: UrlJobRequest):
    """Extract direct stream URLs in-memory for instant Chrome download without pre-saving on disk."""
    if request.output not in {"mp4", "mp3"} or request.bitrate not in {128, 192, 256, 320} or request.quality not in {"high", "standard", "compact"}:
        raise HTTPException(400, "Format atau bitrate tidak didukung.")
    url_value = (request.url or "").strip()
    if not url_value:
        raise HTTPException(400, "Masukkan tautan media yang valid.")

    _purge_expired_streams()
    resolution = classify_url(url_value)
    provider = get_platform_provider(url_value)
    plan: dict | None = None

    if YT_DLP_ENABLED and provider is not None and resolution.status != "invalid_url" and not graph_configured(provider):
        try:
            plan = await ytdlp.resolve_stream_plan(url_value, request.output, request.quality, request.bitrate)
        except RuntimeError as error:
            raise HTTPException(422, {"code": "stream_unavailable", "message": str(error), "next_step": "Periksa tautan atau unggah file langsung."})
    else:
        platform_info = await inspect_platform_source(url_value)
        if platform_info is not None:
            direct_url = platform_info.get("_media_url")
            if not direct_url:
                raise HTTPException(422, {"code": platform_info.get("status", "embed_only"), "message": platform_info.get("message"), "next_step": platform_info.get("next_step")})
            target_url = validate_public_url(direct_url)
            info = {"mime_type": platform_info.get("mime_type") or "video/mp4", "size": platform_info.get("size")}
            title = str(platform_info.get("title") or f"Video {provider.name if provider else 'Media'}")
            author = platform_info.get("author")
            duration = platform_info.get("duration")
            thumbnail = platform_info.get("thumbnail")
        else:
            if not resolution.can_process:
                raise HTTPException(422, {"code": resolution.status, "message": resolution.message, "next_step": resolution.next_step})
            target_url = validate_public_url(url_value)
            info = await inspect_direct_media(target_url)
            title = Path(urlparse(target_url).path).name or "media"
            author = None
            duration = None
            thumbnail = None

        output_name = ytdlp.safe_filename(title, request.output)
        if request.output == "mp3" and info.get("mime_type") != "audio/mpeg":
            plan = {
                "mode": "ffmpeg_mp3",
                "input_url": target_url,
                "headers": {},
                "bitrate": request.bitrate,
                "output_name": output_name,
                "media_type": "audio/mpeg",
                "filesize": None,
                "title": title,
                "author": author,
                "duration": duration,
                "thumbnail": thumbnail,
            }
        else:
            plan = {
                "mode": "direct_proxy",
                "direct_url": target_url,
                "headers": {},
                "filesize": info.get("size"),
                "output_name": output_name,
                "media_type": "audio/mpeg" if request.output == "mp3" else "video/mp4",
                "title": title,
                "author": author,
                "duration": duration,
                "thumbnail": thumbnail,
            }

    token = uuid.uuid4().hex
    STREAM_TOKENS[token] = {**plan, "expires_at": time.time() + 1800}
    return {
        "status": "ready",
        "token": token,
        "download_url": f"/api/stream/{token}",
        "title": plan["title"],
        "author": plan.get("author"),
        "duration": plan.get("duration"),
        "thumbnail": plan.get("thumbnail"),
        "output_name": plan["output_name"],
        "output_kind": request.output,
        "filesize": plan.get("filesize"),
    }


async def _stream_ffmpeg_pipe(cmd: list[str], media_type: str, headers: dict[str, str], chunk_size: int) -> StreamingResponse:
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except FileNotFoundError:
        raise HTTPException(500, "FFmpeg tidak ditemukan di server.")

    stderr_tail = bytearray()

    async def drain_stderr():
        if not proc.stderr:
            return
        while chunk := await proc.stderr.read(4096):
            stderr_tail.extend(chunk)
            if len(stderr_tail) > 4096:
                del stderr_tail[:-4096]

    stderr_task = asyncio.create_task(drain_stderr())
    try:
        first_chunk = await asyncio.wait_for(proc.stdout.read(chunk_size), timeout=30)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        stderr_task.cancel()
        raise HTTPException(504, "Streaming media melewati batas waktu awal.")

    if not first_chunk:
        await proc.wait()
        await stderr_task
        detail = stderr_tail.decode("utf-8", "ignore").strip()[-200:]
        raise HTTPException(502, detail or "Gagal memulai streaming media.")

    async def iter_pipe():
        try:
            yield first_chunk
            while chunk := await proc.stdout.read(chunk_size):
                yield chunk
        finally:
            if proc.returncode is None:
                proc.kill()
            await proc.wait()
            stderr_task.cancel()
            await asyncio.gather(stderr_task, return_exceptions=True)

    return StreamingResponse(iter_pipe(), media_type=media_type, headers=headers)


@app.get("/api/stream/{token}")
async def stream_media(token: str):
    """Stream extracted media directly to browser with Content-Disposition attachment."""
    _purge_expired_streams()
    plan = STREAM_TOKENS.get(token)
    if not plan:
        raise HTTPException(404, "Tautan unduhan sudah kedaluwarsa. Silakan proses ulang link.")

    headers = {
        "Content-Disposition": _content_disposition(plan["output_name"]),
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
    mode = plan["mode"]

    if mode == "direct_proxy":
        timeout = aiohttp.ClientTimeout(total=1800, connect=20, sock_read=60)
        connector = aiohttp.TCPConnector(resolver=PublicAddressResolver(), use_dns_cache=False)
        session = aiohttp.ClientSession(connector=connector, timeout=timeout, trust_env=False)
        upstream_headers = {k: v for k, v in (plan.get("headers") or {}).items() if k.lower() != "host"}
        try:
            upstream = await session.get(plan["direct_url"], headers=upstream_headers, allow_redirects=True)
            if upstream.status >= 400:
                upstream.close()
                await session.close()
                raise HTTPException(502, f"Sumber media menjawab HTTP {upstream.status}.")
        except HTTPException:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            await session.close()
            raise HTTPException(502, "Sumber media tidak dapat dijangkau saat streaming.")

        if upstream.content_length and upstream.content_length <= MAX_REMOTE_BYTES:
            headers["Content-Length"] = str(upstream.content_length)

        async def iter_upstream():
            try:
                async for chunk in upstream.content.iter_chunked(256 * 1024):
                    yield chunk
            finally:
                upstream.close()
                await session.close()

        return StreamingResponse(iter_upstream(), media_type=plan.get("media_type", "video/mp4"), headers=headers)

    if mode == "ffmpeg_mp3":
        input_url = plan["input_url"]
        cmd = [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin",
            *_ffmpeg_header_args(plan.get("headers"), input_url),
            "-i", input_url,
            "-vn", "-codec:a", "libmp3lame", "-compression_level", "2", "-b:a", f"{int(plan.get('bitrate', 192))}k",
            "-f", "mp3", "pipe:1",
        ]
        return await _stream_ffmpeg_pipe(cmd, "audio/mpeg", headers, 64 * 1024)

    if mode == "ffmpeg_mux":
        video_url = plan["video_url"]
        audio_url = plan["audio_url"]
        v_codec = ["-c:v", "copy"] if plan.get("video_copy", True) else ["-c:v", "libx264", "-preset", "superfast", "-crf", "23"]
        a_codec = ["-c:a", "copy"] if plan.get("audio_copy", True) else ["-c:a", "aac", "-b:a", "192k"]
        cmd = [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin",
            *_ffmpeg_header_args(plan.get("video_headers"), video_url), "-i", video_url,
            *_ffmpeg_header_args(plan.get("audio_headers"), audio_url), "-i", audio_url,
            "-map", "0:v:0", "-map", "1:a:0",
            *v_codec, *a_codec,
            "-f", "mp4", "-movflags", "frag_keyframe+empty_moov+default_base_moof", "pipe:1",
        ]
        return await _stream_ffmpeg_pipe(cmd, "video/mp4", headers, 128 * 1024)

    raise HTTPException(500, "Mode streaming tidak dikenal.")


@app.post("/api/previews", status_code=201)
async def create_preview(request: UrlJobRequest):
    if len(PREVIEWS) >= MAX_ACTIVE_PREVIEWS:
        raise HTTPException(429, "Terlalu banyak pratinjau aktif. Tunggu sebentar lalu coba lagi.")
    if not request.url:
        raise HTTPException(400, "Masukkan URL HTTPS langsung ke file audio atau video.")
    resolution = classify_url(request.url)
    platform_info = await inspect_platform_source(request.url)
    if platform_info is not None:
        url = platform_info.get("_media_url")
        if not url:
            raise HTTPException(422, {"code": platform_info.get("status", "embed_only"), "message": platform_info.get("message"), "next_step": platform_info.get("next_step")})
        url = validate_public_url(url)
    else:
        if not resolution.can_process:
            raise HTTPException(422, {"code": resolution.status, "message": resolution.message, "next_step": resolution.next_step})
        url = validate_public_url(request.url)
    preview_id = uuid.uuid4().hex
    path = UPLOAD_DIR / f"{preview_id}.preview"
    try:
        content_type, size = await fetch_direct_media(url, path, None)
        metadata = await probe(path)
    except HTTPException:
        path.unlink(missing_ok=True)
        raise
    except RuntimeError as error:
        path.unlink(missing_ok=True)
        raise HTTPException(422, {"code": "unsupported_media", "message": str(error), "next_step": "Pilih file audio/video yang didukung atau unggah file hasil ekspor dari platform."})
    except Exception:
        path.unlink(missing_ok=True)
        raise HTTPException(502, {"code": "source_unavailable", "message": "Sumber dapat diakses URL-nya, tetapi backend gagal mengambil atau memeriksa file media.", "next_step": "Pastikan URL publik, tidak membutuhkan login, dan mengarah langsung ke file media."})
    has_video = any(stream.get("codec_type") == "video" for stream in metadata["streams"])
    has_audio = any(stream.get("codec_type") == "audio" for stream in metadata["streams"])
    video_stream = next((stream for stream in metadata["streams"] if stream.get("codec_type") == "video"), {})
    audio_stream = next((stream for stream in metadata["streams"] if stream.get("codec_type") == "audio"), {})
    if not has_video and not has_audio:
        path.unlink(missing_ok=True)
        raise HTTPException(415, "Sumber tidak memiliki audio atau video yang bisa diputar.")
    format_name = metadata.get("format_name", "")
    mime_type = "video/mp4" if has_video and any(name in format_name for name in ("mp4", "mov")) else "video/webm" if has_video and "webm" in format_name else "video/x-matroska" if has_video and "matroska" in format_name else "video/mp4" if has_video else "audio/mpeg" if "mp3" in format_name else "audio/mp4" if "mp4" in format_name else "audio/ogg" if "ogg" in format_name else "audio/mpeg"
    title = Path(urlparse(url).path).name or "Media langsung"
    PREVIEWS[preview_id] = {"path": str(path), "filename": title[:180], "mime_type": mime_type, "size": size, "duration": metadata["duration"], "expires_at": time.time() + PREVIEW_TTL_SECONDS}
    resolution = f"{video_stream['width']}×{video_stream['height']}" if video_stream.get("width") and video_stream.get("height") else None
    return {"id": preview_id, "title": title[:180], "mime_type": mime_type, "size": size,
            "duration": metadata["duration"], "format": format_name, "resolution": resolution,
            "video_codec": video_stream.get("codec_name"), "audio_codec": audio_stream.get("codec_name"),
            "formats": [{"container": format_name, "resolution": resolution, "size": size}],
            "metadata_available": True, "player_url": f"/api/previews/{preview_id}/media"}


@app.get("/api/previews/{preview_id}/media")
async def preview_media(preview_id: str):
    preview = PREVIEWS.get(preview_id)
    if not preview or preview["expires_at"] <= time.time():
        raise HTTPException(404, "Pratinjau sudah kedaluwarsa. Buat pratinjau baru.")
    path = Path(preview["path"]).resolve()
    if path.parent != UPLOAD_DIR.resolve() or not path.is_file():
        raise HTTPException(404, "File pratinjau tidak tersedia.")
    return FileResponse(path, media_type=preview["mime_type"], headers={"Content-Disposition": "inline", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@app.post("/api/jobs/upload", status_code=202)
async def upload_job(file: UploadFile = File(...), output: str = Form("mp3"), bitrate: int = Form(192), quality: str = Form("standard")):
    ensure_job_capacity()
    if output not in {"mp3", "mp4"}:
        raise HTTPException(400, "Format keluaran harus MP3 atau MP4.")
    if bitrate not in {128, 192, 256, 320}:
        raise HTTPException(400, "Bitrate harus 128, 192, 256, atau 320 kbps.")
    if quality not in {"high", "standard", "compact"}:
        raise HTTPException(400, "Kualitas video tidak didukung.")
    if not file.filename or Path(file.filename).name != file.filename:
        raise HTTPException(400, "Nama file tidak valid.")
    job = create_job(file.filename[:180], output, bitrate, quality)
    input_path = UPLOAD_DIR / f"{uuid.uuid4().hex}.upload"
    total = 0
    try:
        with input_path.open("wb") as target:
            while chunk := await file.read(1024 * 256):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, f"File melebihi batas upload {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
                target.write(chunk)
    except Exception:
        input_path.unlink(missing_ok=True)
        JOBS.pop(job["id"], None)
        raise
    finally:
        await file.close()
    if total == 0:
        input_path.unlink(missing_ok=True)
        JOBS.pop(job["id"], None)
        raise HTTPException(400, "File kosong.")
    start_job(job, input_path)
    return public_job(job)


@app.post("/api/jobs/download", status_code=202)
@app.post("/api/jobs/convert", status_code=202)
@app.post("/api/jobs/url", status_code=202, include_in_schema=False)
async def url_job(request: UrlJobRequest):
    ensure_job_capacity()
    if request.output not in {"mp4", "mp3"} or request.bitrate not in {128, 192, 256, 320} or request.quality not in {"high", "standard", "compact"}:
        raise HTTPException(400, "Format atau bitrate tidak didukung.")
    if request.preview_id:
        preview = PREVIEWS.pop(request.preview_id, None)
        if not preview or preview["expires_at"] <= time.time():
            if preview:
                Path(preview["path"]).unlink(missing_ok=True)
            raise HTTPException(404, "Pratinjau tidak tersedia lagi. Buat pratinjau baru.")
        input_path = Path(preview["path"]).resolve()
        if input_path.parent != UPLOAD_DIR.resolve() or not input_path.is_file():
            raise HTTPException(404, "File media pratinjau tidak tersedia.")
        job = create_job(preview["filename"], request.output, request.bitrate, request.quality)
        start_job(job, input_path)
        return public_job(job)
    if not request.url or not request.url.strip():
        raise HTTPException(400, "Masukkan URL HTTPS langsung ke file media atau buat pratinjau terlebih dahulu.")
    url_value = request.url.strip()
    resolution = classify_url(url_value)
    provider = get_platform_provider(url_value)
    if YT_DLP_ENABLED and provider is not None and resolution.status != "invalid_url" and not graph_configured(provider):
        return await start_youtube_job(request, provider.name)
    platform_info = await inspect_platform_source(url_value)
    if platform_info is not None:
        url = platform_info.get("_media_url")
        if not url:
            raise HTTPException(422, {"code": platform_info.get("status", "embed_only"), "message": platform_info.get("message"), "next_step": platform_info.get("next_step")})
        url = validate_public_url(url)
    else:
        if not resolution.can_process:
            raise HTTPException(422, {"code": resolution.status, "message": resolution.message, "next_step": resolution.next_step})
        url = validate_public_url(url_value)
    path = urlparse(url).path
    name = Path(path).name[:140] or "media"
    job = create_job(name, request.output, request.bitrate, request.quality)
    job["stage"] = "Menunggu proses"
    async def fetch_and_process():
        input_path = UPLOAD_DIR / f"{uuid.uuid4().hex}.source"
        job["_input_path"] = str(input_path)
        try:
            await fetch_direct_media(url, input_path, job["id"])
            TASKS[job["id"]] = asyncio.create_task(run_job(job["id"], input_path))
            await TASKS[job["id"]]
        except asyncio.CancelledError:
            input_path.unlink(missing_ok=True)
            raise
        except Exception as error:
            input_path.unlink(missing_ok=True)
            if isinstance(error, HTTPException) and isinstance(error.detail, dict):
                detail = error.detail
                message = " ".join(part for part in (detail.get("message"), detail.get("next_step")) if part)
                update_job(job["id"], status="failed", stage="Gagal", message=message or "Sumber media gagal diproses.", error_code=detail.get("code"), next_step=detail.get("next_step"))
            else:
                message = error.detail if isinstance(error, HTTPException) else "Sumber media tidak dapat diakses atau ditolak oleh validasi keamanan."
                update_job(job["id"], status="failed", stage="Gagal", message=str(message))
    TASKS[job["id"]] = asyncio.create_task(fetch_and_process())
    return public_job(job)


def graph_configured(provider) -> bool:
    """Instagram/Facebook with an official Graph API token keep using the authorized path."""
    if provider.name == "Instagram":
        return bool(os.getenv("META_INSTAGRAM_ACCESS_TOKEN", "").strip() and os.getenv("META_INSTAGRAM_USER_ID", "").strip())
    if provider.name == "Facebook":
        return bool(os.getenv("META_GRAPH_ACCESS_TOKEN", "").strip())
    return False


async def start_youtube_job(request: UrlJobRequest, platform: str = "YouTube") -> dict:
    job = create_job(platform, request.output, request.bitrate, request.quality)
    update_job(job["id"], status="processing", stage=f"Mengunduh dari {platform}", progress=0, message="Mengambil video dengan yt-dlp.")
    url_value = (request.url or "").strip()

    async def fetch_and_process():
        input_path = None
        try:
            input_path = await ytdlp.download(
                url_value,
                request.output,
                request.quality,
                lambda pct: update_job(job["id"], progress=pct),
                on_title=lambda title: job.update(filename=title[:180]) if title else None,
            )
            job["_input_path"] = str(input_path)
            TASKS[job["id"]] = asyncio.create_task(run_job(job["id"], input_path))
            await TASKS[job["id"]]
        except asyncio.CancelledError:
            if input_path:
                input_path.unlink(missing_ok=True)
            raise
        except Exception as error:
            if input_path:
                input_path.unlink(missing_ok=True)
            message = str(error) if isinstance(error, RuntimeError) else f"Video {platform} gagal diproses."
            update_job(job["id"], status="failed", stage="Gagal", message=message)
    TASKS[job["id"]] = asyncio.create_task(fetch_and_process())
    return public_job(job)


@app.get("/api/jobs")
async def recent_jobs():
    mine = [job for job in JOBS.values() if job.get("_owner") == OWNER.get()]
    return [public_job(job) for job in sorted(mine, key=lambda item: item["created_at"], reverse=True)[:30]]


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = owned_job(job_id)
    if not job:
        raise HTTPException(404, "Pekerjaan tidak ditemukan atau sudah kedaluwarsa.")
    return public_job(job)


@app.get("/api/jobs/{job_id}/download")
async def download_job(job_id: str):
    job = owned_job(job_id)
    if not job or job.get("status") != "completed" or not job.get("_output_path"):
        raise HTTPException(404, "Hasil belum tersedia atau sudah kedaluwarsa.")
    path = Path(job["_output_path"]).resolve()
    if path.parent != OUTPUT_DIR.resolve() or not path.is_file():
        raise HTTPException(404, "File hasil tidak tersedia.")
    return FileResponse(path, filename=job["output_name"], media_type="audio/mpeg" if job["output_kind"] == "mp3" else "video/mp4")


@app.delete("/api/jobs/{job_id}", status_code=204)
async def remove_job(job_id: str):
    if not owned_job(job_id) or not await delete_job(job_id):
        raise HTTPException(404, "Pekerjaan tidak ditemukan.")


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job_endpoint(job_id: str):
    if not owned_job(job_id) or not await cancel_job(job_id):
        job = owned_job(job_id)
        if not job:
            raise HTTPException(404, "Pekerjaan tidak ditemukan.")
        raise HTTPException(409, "Pekerjaan sudah selesai atau tidak dapat dibatalkan.")
    return public_job(JOBS[job_id])


# Terakhir: rute satu-segmen ini tidak boleh menimpa rute lain.
@app.get("/{slug}", include_in_schema=False)
async def content_page(slug: str):
    body = pages.render_home(slug) if slug in pages.HOME_PAGES else pages.render_static(slug)
    if body is None:
        raise HTTPException(404, "Halaman tidak ditemukan.")
    return HTMLResponse(body, headers={"Cache-Control": "no-cache"})
