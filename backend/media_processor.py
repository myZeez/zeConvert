import asyncio
import json
import math
import os
import re
from pathlib import Path

from .config import (
    FFMPEG,
    FFPROBE,
    MAX_MEDIA_SECONDS,
    MAX_OUTPUT_BYTES,
    MAX_PROCESS_SECONDS,
    OUTPUT_DIR,
    PARALLEL_SEGMENT_SECONDS,
    PARALLEL_THRESHOLD_SECONDS,
    PARALLEL_WORKERS,
    UPLOAD_DIR,
)


async def probe(path: Path) -> dict:
    try:
        proc = await asyncio.create_subprocess_exec(
            FFPROBE, "-v", "error", "-show_entries", "format=duration,format_name,size:stream=codec_type,codec_name,width,height,bit_rate,sample_rate,channels",
            "-of", "json", str(path), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
    except FileNotFoundError:
        raise RuntimeError("FFprobe tidak ditemukan. Pasang FFmpeg lalu cek PATH.")
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError("Pemeriksaan media melewati batas waktu.")
    if proc.returncode != 0:
        raise RuntimeError("File tidak terbaca sebagai media audio atau video yang valid.")
    try:
        data = json.loads(stdout)
        duration = float(data.get("format", {}).get("duration", 0))
    except (ValueError, TypeError, json.JSONDecodeError):
        raise RuntimeError("Metadata file media tidak dapat dibaca.")
    streams = data.get("streams", [])
    if not any(stream.get("codec_type") in ("audio", "video") for stream in streams):
        raise RuntimeError("File ini tidak memiliki stream audio atau video.")
    if duration <= 0:
        raise RuntimeError("Durasi media tidak valid.")
    if duration > MAX_MEDIA_SECONDS:
        raise RuntimeError(f"Durasi media melebihi batas {MAX_MEDIA_SECONDS // 60} menit.")
    return {"duration": duration, "streams": streams, "format_name": data.get("format", {}).get("format_name", "")}


async def _run_ffmpeg(args: list[str], on_out_seconds=None, timeout: float = MAX_PROCESS_SECONDS) -> int:
    try:
        proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except FileNotFoundError:
        raise RuntimeError("FFmpeg tidak ditemukan. Pasang FFmpeg lalu tambahkan ke PATH atau atur FFMPEG_PATH.")

    async def read_progress():
        while line := await proc.stdout.readline():
            text = line.decode("utf-8", "ignore").strip()
            if text.startswith("out_time_us=") and on_out_seconds is not None:
                try:
                    on_out_seconds(int(text.split("=", 1)[1]) / 1_000_000)
                except ValueError:
                    pass

    async def read_stderr():
        while await proc.stderr.read(8192):
            pass

    reader = asyncio.create_task(read_progress())
    stderr_reader = asyncio.create_task(read_stderr())
    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
        await reader
        await stderr_reader
        return proc.returncode or 0
    except (asyncio.TimeoutError, asyncio.CancelledError):
        proc.kill()
        await proc.wait()
        reader.cancel()
        stderr_reader.cancel()
        await asyncio.gather(reader, stderr_reader, return_exceptions=True)
        if asyncio.current_task() and asyncio.current_task().cancelling():
            raise
        raise RuntimeError("Pemrosesan melewati batas waktu.")


async def _encode_parallel_segments(job_id: str, input_path: Path, output_path: Path, duration: float, kind: str, job: dict) -> None:
    from .job_manager import update_job

    base_seg = max(1, int(PARALLEL_SEGMENT_SECONDS))
    seg_len = max(base_seg, math.ceil(duration / 12)) if base_seg >= 60 else base_seg
    starts = [i * seg_len for i in range(max(1, math.ceil(duration / seg_len)))]
    min_tail = min(15.0, seg_len * 0.25) if seg_len >= 60 else 0.5
    if len(starts) > 1 and (duration - starts[-1]) < min_tail:
        starts.pop()
    total = len(starts)
    seg_durations = [
        (duration - start) if idx == total - 1 else float(seg_len)
        for idx, start in enumerate(starts)
    ]
    workers = max(1, int(PARALLEL_WORKERS))
    threads = str(max(1, (os.cpu_count() or 2) // workers))
    bitrate = int(job["bitrate"])
    quality_crf = {"high": "20", "standard": "23", "compact": "28"}.get(job.get("quality", "standard"), "23")
    stage = f"Mengonversi paralel ({total} bagian)"
    update_job(job_id, stage=stage, progress=1, message=f"Memproses {total} bagian secara paralel ({workers} worker).")

    seg_paths = [UPLOAD_DIR / f"{job_id}.part{idx:04d}.{kind}" for idx in range(total)]
    concat_list = UPLOAD_DIR / f"{job_id}.concat.txt"
    seg_progress = [0.0] * total
    last_pct = 1
    sem = asyncio.Semaphore(workers)

    def report_progress(idx: int, seconds: float) -> None:
        nonlocal last_pct
        seg_progress[idx] = min(seg_durations[idx], max(0.0, seconds))
        overall = min(96, max(1, int(sum(seg_progress) / duration * 96)))
        if overall > last_pct:
            last_pct = overall
            update_job(job_id, stage=stage, progress=overall)

    async def encode_one(idx: int) -> None:
        start = starts[idx]
        seg_path = seg_paths[idx]
        cmd = [FFMPEG, "-hide_banner", "-nostdin", "-y", "-ss", f"{start:.3f}", "-i", str(input_path)]
        if idx < total - 1:
            cmd.extend(["-t", f"{seg_len:.3f}"])
        if kind == "mp3":
            cmd.extend(["-vn", "-codec:a", "libmp3lame", "-compression_level", "2", "-b:a", f"{bitrate}k", "-write_xing", "0", "-threads", threads])
        else:
            cmd.extend(["-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "superfast", "-crf", quality_crf, "-c:a", "aac", "-b:a", "192k", "-threads", threads, "-avoid_negative_ts", "make_zero"])
        cmd.extend(["-progress", "pipe:1", "-nostats", str(seg_path)])

        async with sem:
            for _attempt in range(2):
                rc = await _run_ffmpeg(cmd, on_out_seconds=lambda s, i=idx: report_progress(i, s), timeout=MAX_PROCESS_SECONDS)
                if rc == 0 and seg_path.exists() and seg_path.stat().st_size > 0:
                    seg_progress[idx] = seg_durations[idx]
                    return
                seg_progress[idx] = 0.0
                seg_path.unlink(missing_ok=True)
            if idx == total - 1 and total > 1:
                seg_progress[idx] = seg_durations[idx]
                return
            raise RuntimeError(f"FFmpeg gagal memproses bagian {idx + 1}/{total}.")

    tasks = [asyncio.create_task(encode_one(i)) for i in range(total)]
    try:
        try:
            await asyncio.gather(*tasks)
        except BaseException:
            for t in tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

        def _concat_entry(path: Path) -> str:
            escaped = path.resolve().as_posix().replace("'", r"'\''")
            return f"file '{escaped}'"

        valid_seg_paths = [p for p in seg_paths if p.exists() and p.stat().st_size > 0]
        if not valid_seg_paths:
            raise RuntimeError("FFmpeg gagal memproses bagian media.")
        concat_list.write_text("\n".join(_concat_entry(p) for p in valid_seg_paths) + "\n", encoding="utf-8")
        update_job(job_id, stage="Menggabungkan bagian", progress=97, message=f"Menggabungkan {len(valid_seg_paths)} bagian menjadi file akhir.")
        concat_args = [
            FFMPEG, "-hide_banner", "-nostdin", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy", "-fs", str(MAX_OUTPUT_BYTES),
            *(["-movflags", "+faststart"] if kind == "mp4" else []),
            "-progress", "pipe:1", "-nostats", str(output_path),
        ]
        rc = await _run_ffmpeg(concat_args, timeout=MAX_PROCESS_SECONDS)
        if rc != 0 or not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("FFmpeg gagal menggabungkan bagian media.")
    finally:
        for seg_path in seg_paths:
            seg_path.unlink(missing_ok=True)
        concat_list.unlink(missing_ok=True)


async def process_media(job_id: str, input_path: Path) -> None:
    from .job_manager import JOBS, update_job
    update_job(job_id, status="processing", stage="Memvalidasi media", progress=0, message="Memeriksa isi dan durasi media.")
    metadata = await probe(input_path)
    job = JOBS[job_id]
    kind = job["output_kind"]
    if kind == "mp3" and not any(s.get("codec_type") == "audio" for s in metadata["streams"]):
        raise RuntimeError("File ini tidak berisi audio untuk dikonversi.")
    if kind == "mp4" and not any(s.get("codec_type") == "video" for s in metadata["streams"]):
        raise RuntimeError("File ini tidak berisi video untuk dibuat menjadi MP4.")
    output_path = OUTPUT_DIR / f"{job_id}.{kind}"
    job["_output_path"] = str(output_path)
    compatible = False
    video_copy_compatible = False
    if kind == "mp4":
        video = next(s for s in metadata["streams"] if s.get("codec_type") == "video")
        audio_streams = [s for s in metadata["streams"] if s.get("codec_type") == "audio"]
        video_copy_compatible = video.get("codec_name") == "h264"
        compatible = (
            video_copy_compatible
            and all(s.get("codec_name") == "aac" for s in audio_streams)
            and any(name in metadata.get("format_name", "") for name in ("mp4", "mov"))
        )

    use_parallel = (
        metadata["duration"] > PARALLEL_THRESHOLD_SECONDS
        and PARALLEL_WORKERS > 1
        and (kind == "mp3" or not video_copy_compatible)
    )
    if use_parallel:
        await _encode_parallel_segments(job_id, input_path, output_path, metadata["duration"], kind, job)
    else:
        update_job(job_id, stage="Mengonversi media", progress=1, message="Sedang mengonversi media ke format pilihanmu.")
        bitrate = int(job["bitrate"])
        if kind == "mp3":
            args = [FFMPEG, "-hide_banner", "-nostdin", "-y", "-i", str(input_path), "-vn", "-codec:a", "libmp3lame", "-compression_level", "2", "-b:a", f"{bitrate}k", "-fs", str(MAX_OUTPUT_BYTES), "-progress", "pipe:1", "-nostats", str(output_path)]
        elif compatible:
            args = [FFMPEG, "-hide_banner", "-nostdin", "-y", "-i", str(input_path), "-map", "0:v:0", "-map", "0:a?", "-c", "copy", "-fs", str(MAX_OUTPUT_BYTES), "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(output_path)]
        elif video_copy_compatible:
            args = [FFMPEG, "-hide_banner", "-nostdin", "-y", "-i", str(input_path), "-map", "0:v:0", "-map", "0:a?", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-fs", str(MAX_OUTPUT_BYTES), "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(output_path)]
        else:
            quality_crf = {"high": "20", "standard": "23", "compact": "28"}.get(job.get("quality", "standard"), "23")
            args = [FFMPEG, "-hide_banner", "-nostdin", "-y", "-i", str(input_path), "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "superfast", "-crf", quality_crf, "-c:a", "aac", "-b:a", "192k", "-fs", str(MAX_OUTPUT_BYTES), "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(output_path)]
        last_pct = 0
        def on_single_sec(seconds: float) -> None:
            nonlocal last_pct
            percent = min(99, max(1, int(seconds / metadata["duration"] * 100)))
            if percent > last_pct:
                last_pct = percent
                update_job(job_id, progress=percent, stage="Mengonversi media")
        rc = await _run_ffmpeg(args, on_out_seconds=on_single_sec, timeout=MAX_PROCESS_SECONDS)
        if rc != 0 or not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("FFmpeg gagal memproses media. Periksa apakah file berisi stream yang didukung.")
    if output_path.stat().st_size >= MAX_OUTPUT_BYTES:
        raise RuntimeError("Hasil melewati batas ukuran output yang diizinkan.")
    update_job(job_id, stage="Memvalidasi hasil", progress=99, message="Memeriksa file keluaran.")
    output_metadata = await probe(output_path)
    if output_metadata["duration"] < min(metadata["duration"] * 0.9, metadata["duration"] - 2.0):
        raise RuntimeError("Hasil tidak lengkap dan tidak dapat digunakan.")
    output_streams = output_metadata["streams"]
    if kind == "mp4":
        if not any(s.get("codec_type") == "video" and s.get("codec_name") == "h264" for s in output_streams):
            raise RuntimeError("Validasi hasil gagal: MP4 tidak berisi video H.264.")
        if any(s.get("codec_type") == "audio" for s in output_streams) and not any(s.get("codec_type") == "audio" and s.get("codec_name") == "aac" for s in output_streams):
            raise RuntimeError("Validasi hasil gagal: audio MP4 tidak berformat AAC.")
    elif not any(s.get("codec_type") == "audio" and s.get("codec_name") == "mp3" for s in output_streams):
        raise RuntimeError("Validasi hasil gagal: output tidak berformat audio MP3.")
    raw_stem = re.sub(r"\.(?:mp4|mp3|mkv|webm|mov|avi|m4a|wav|ogg|flac|aac)$", "", job["filename"], flags=re.IGNORECASE)
    safe_stem = re.sub(r"[^\w .()-]", "_", raw_stem, flags=re.UNICODE).strip(" .")[:100] or "media"
    update_job(job_id, status="completed", stage="Selesai", progress=100, message="File siap diunduh.", output_name=f"{safe_stem}.{kind}", output_size=output_path.stat().st_size)
