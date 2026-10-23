"""Local source-bound checks and actual decoded-frame/audio export verification."""
from __future__ import annotations

from fractions import Fraction
import json
import math
from pathlib import Path
import subprocess

from .plan import Plan, PlanError

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def _probe(path: Path, ffprobe: str, *, count_frames=False) -> dict:
    command = [ffprobe, "-v", "error"]
    if count_frames:
        command.append("-count_frames")
    command += ["-show_streams", "-show_format", "-of", "json", str(path)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=180)
        data = json.loads(result.stdout)
        if not isinstance(data, dict):
            raise ValueError("probe result not an object")
        return data
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise PlanError("FFprobe could not inspect media for quality checks") from exc


def _duration(stream: dict, container: dict) -> float:
    try:
        seconds = float(stream.get("duration") or container["duration"])
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("invalid duration")
        return seconds
    except (TypeError, KeyError, ValueError) as exc:
        raise PlanError("media has no reliable finite positive duration") from exc


def check_sources(plan: Plan, *, ffprobe="ffprobe"):
    """Do not silently pad a video whose requested source range does not exist."""
    cache = {}
    for clip in (*plan.videos, *plan.audios):
        if clip.kind == "video" and clip.path.suffix.lower() in IMAGE_EXTENSIONS:
            continue
        if clip.path not in cache:
            cache[clip.path] = _probe(clip.path, ffprobe)
        data = cache[clip.path]
        kind = "video" if clip.kind == "video" else "audio"
        streams = [s for s in data.get("streams", []) if s.get("codec_type") == kind]
        if not streams:
            raise PlanError(f"source has no {kind} stream: {clip.path}")
        duration = _duration(streams[0], data.get("format", {}))
        end = (clip.source_start_ms + clip.duration_ms * clip.speed) / 1000
        if end > duration + max(0.05, 1 / plan.fps):
            raise PlanError(f"requested {kind} source range exceeds media duration: {clip.path}")


def verify_output(plan: Plan, path: Path, *, ffprobe="ffprobe", ffmpeg="ffmpeg", decode=True) -> dict:
    data = _probe(path, ffprobe, count_frames=True)
    video = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    audio = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
    if len(video) != 1 or len(audio) != 1:
        raise PlanError("export must contain exactly one video and one audio stream")
    v, a = video[0], audio[0]
    try:
        fps = float(Fraction(v["avg_frame_rate"]))
        frames = int(v["nb_read_frames"])
        width, height = int(v["width"]), int(v["height"])
        video_start, audio_start = float(v.get("start_time", 0)), float(a.get("start_time", 0))
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise PlanError("export lacks usable frame count, frame rate, dimensions or start times") from exc
    expected = plan.duration_ms / 1000
    tolerance = max(0.25, 2 / plan.fps)
    video_duration = _duration(v, data.get("format", {}))
    audio_duration = _duration(a, data.get("format", {}))
    duration = _duration({}, data.get("format", {}))
    if (width, height) != (plan.width, plan.height) or abs(fps - plan.fps) > 0.01:
        raise PlanError("export canvas or frame rate mismatch")
    if abs(frames - round(expected * plan.fps)) > 2:
        raise PlanError("export decoded frame count does not match planned duration")
    if any(abs(d - expected) > tolerance for d in [duration, video_duration, audio_duration]):
        raise PlanError("export stream/container duration mismatch")
    if any(not math.isfinite(t) or abs(t) > tolerance for t in [video_start, audio_start]):
        raise PlanError("export streams do not begin at timeline origin")
    if abs(video_duration - audio_duration) > tolerance:
        raise PlanError("export audio/video duration drift")
    if decode:
        try:
            subprocess.run([ffmpeg, "-v", "error", "-xerror", "-nostdin", "-i", str(path),
                            "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"],
                           capture_output=True, check=True, timeout=600)
        except (OSError, subprocess.SubprocessError) as exc:
            raise PlanError("export failed complete audio/video decode verification") from exc
    return {"schema": "video-clips/export-quality/v1", "duration_s": duration,
            "video_duration_s": video_duration, "audio_duration_s": audio_duration,
            "width": width, "height": height, "fps": fps, "decoded_frames": frames,
            "expected_frames": round(expected * plan.fps), "decode_verified": decode,
            "scope": "stream/frame/timing/decode checks; not perceptual lip-sync or factual transcript verification"}
