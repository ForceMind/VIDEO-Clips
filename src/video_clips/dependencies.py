"""Probe actual FFmpeg build features before an optional paid editing step."""
from functools import lru_cache
from pathlib import Path
import shutil
import subprocess

from .plan import PlanError


@lru_cache(maxsize=8)
def _subtitle_filter(binary: str, modified_ns: int, size: int) -> bool:
    try:
        result = subprocess.run([binary, "-hide_banner", "-filters"], capture_output=True,
            encoding="utf-8", errors="replace", check=True, timeout=20)
        return any(len(parts := line.split()) > 1 and parts[1] == "subtitles"
                   for line in result.stdout.splitlines())
    except (OSError, subprocess.SubprocessError):
        return False


def ffmpeg_features(ffmpeg="ffmpeg") -> dict:
    found = shutil.which(ffmpeg)
    if not found:
        return {"available": False, "subtitles_filter": False}
    binary = Path(found).resolve()
    info = binary.stat()
    return {"available": True, "subtitles_filter": _subtitle_filter(str(binary), info.st_mtime_ns, info.st_size)}


def require_subtitle_filter(ffmpeg="ffmpeg"):
    if not ffmpeg_features(ffmpeg)["subtitles_filter"]:
        raise PlanError("FFmpeg build lacks the subtitles/libass filter. Install a full build; "
                        "on macOS use ffmpeg-full and put its bin directory first on PATH.")
