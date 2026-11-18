import asyncio
import contextvars
import logging
import time
import uuid
from pathlib import Path

from .config import JOB_TTL_SECONDS, MAX_CONCURRENT_JOBS, OUTPUT_DIR, UPLOAD_DIR
from .media_processor import process_media

logger = logging.getLogger("putarvideo.jobs")

OWNER: contextvars.ContextVar[str | None] = contextvars.ContextVar("job_owner", default=None)
JOBS: dict[str, dict] = {}
TASKS: dict[str, asyncio.Task] = {}
SLOTS = asyncio.Semaphore(MAX_CONCURRENT_JOBS)


def public_job(job: dict) -> dict:
    return {key: value for key, value in job.items() if not key.startswith("_")}


def create_job(filename: str, output_kind: str, bitrate: int, quality: str = "standard") -> dict:
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "filename": filename,
        "output_kind": output_kind,
        "bitrate": bitrate,
        "quality": quality,
        "status": "queued",
        "stage": "Menunggu proses",
        "progress": 0,
        "message": "Pekerjaan masuk antrean.",
        "created_at": time.time(),
        "updated_at": time.time(),
        "output_name": None,
        "output_size": None,
        "_input_path": None,
        "_output_path": None,
        "_owner": OWNER.get(),
    }
    JOBS[job_id] = job
    return job


def update_job(job_id: str, **values) -> None:
    job = JOBS.get(job_id)
    if job:
        job.update(values, updated_at=time.time())


async def run_job(job_id: str, input_path: Path) -> None:
    job = JOBS[job_id]
    async with SLOTS:
        try:
            await process_media(job_id, input_path)
        except asyncio.CancelledError:
            update_job(job_id, status="canceled", stage="Dibatalkan", progress=None, message="Pekerjaan dibatalkan.")
            raise
        except Exception as error:
            logger.exception("Media processing failed for job %s", job_id)
            output_path = job.get("_output_path")
            if output_path:
                Path(output_path).unlink(missing_ok=True)
            message = str(error) if isinstance(error, RuntimeError) else "Pemrosesan gagal karena kesalahan internal."
            update_job(job_id, status="failed", stage="Gagal", message=message or "Pemrosesan gagal.")
        finally:
            input_path.unlink(missing_ok=True)


def start_job(job: dict, input_path: Path) -> None:
    job["_input_path"] = str(input_path)
    TASKS[job["id"]] = asyncio.create_task(run_job(job["id"], input_path))


async def cancel_job(job_id: str) -> bool:
    job = JOBS.get(job_id)
    if not job:
        return False
    if job["status"] not in {"queued", "processing"}:
        return False
    task = TASKS.get(job_id)
    update_job(job_id, status="canceled", stage="Dibatalkan", progress=None, message="Pekerjaan dibatalkan.")
    if task and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    return True


async def delete_job(job_id: str) -> bool:
    job = JOBS.pop(job_id, None)
    if not job:
        return False
    task = TASKS.pop(job_id, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    for key in ("_input_path", "_output_path"):
        value = job.get(key)
        if value:
            Path(value).unlink(missing_ok=True)
    return True


async def cleanup_expired() -> None:
    cutoff = time.time() - JOB_TTL_SECONDS
    for job_id, job in list(JOBS.items()):
        if job["updated_at"] < cutoff:
            await delete_job(job_id)
    for folder in (UPLOAD_DIR, OUTPUT_DIR):
        for item in folder.iterdir():
            try:
                if item.is_file() and item.stat().st_mtime < cutoff:
                    item.unlink(missing_ok=True)
            except OSError:
                pass
