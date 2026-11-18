import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
FRONTEND_DIR = ROOT / "frontend"
storage_setting = Path(os.getenv("STORAGE_DIR", str(ROOT / "storage")))
STORAGE_DIR = (ROOT / storage_setting).resolve() if not storage_setting.is_absolute() else storage_setting.resolve()
UPLOAD_DIR = STORAGE_DIR / "uploads"
OUTPUT_DIR = STORAGE_DIR / "outputs"
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "2048")) * 1024 * 1024
MAX_REMOTE_BYTES = int(os.getenv("MAX_REMOTE_MB", "2048")) * 1024 * 1024
MAX_MEDIA_SECONDS = int(os.getenv("MAX_MEDIA_SECONDS", str(6 * 60 * 60)))
MAX_PROCESS_SECONDS = int(os.getenv("MAX_PROCESS_SECONDS", str(90 * 60)))
JOB_TTL_SECONDS = int(os.getenv("JOB_TTL_SECONDS", str(60 * 60)))
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "2"))
MAX_ACTIVE_JOBS = int(os.getenv("MAX_ACTIVE_JOBS", "10"))
MAX_ACTIVE_PREVIEWS = int(os.getenv("MAX_ACTIVE_PREVIEWS", "3"))
PREVIEW_TTL_SECONDS = int(os.getenv("PREVIEW_TTL_SECONDS", "600"))
MAX_OUTPUT_BYTES = int(os.getenv("MAX_OUTPUT_MB", "2048")) * 1024 * 1024
FFMPEG = os.getenv("FFMPEG_PATH", "ffmpeg")
FFPROBE = os.getenv("FFPROBE_PATH", "ffprobe")
YT_DLP_ENABLED = os.getenv("YT_DLP_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
YT_DLP_TIMEOUT_SECONDS = int(os.getenv("YT_DLP_TIMEOUT_SECONDS", "45"))
PARALLEL_THRESHOLD_SECONDS = int(os.getenv("PARALLEL_THRESHOLD_SECONDS", "1200"))
PARALLEL_SEGMENT_SECONDS = int(os.getenv("PARALLEL_SEGMENT_SECONDS", "300"))
PARALLEL_WORKERS = max(1, int(os.getenv("PARALLEL_WORKERS", str(max(2, min(4, os.cpu_count() or 2))))))

for directory in (UPLOAD_DIR, OUTPUT_DIR):
    directory.mkdir(parents=True, exist_ok=True)
