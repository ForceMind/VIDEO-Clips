"""Standalone StepAudio 2.5 ASR SSE client; text-only and explicit-pay only.

The provider's streamed transcript does not itself establish word-level timestamps.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.error
import urllib.request

ENDPOINT = "https://api.stepfun.com/v1/audio/asr/sse"
SUPPORTED = {".mp3": "mp3", ".wav": "wav", ".ogg": "ogg", ".opus": "ogg"}


class ASRError(RuntimeError):
    pass


def parse_sse(lines) -> dict:
    """Parse Step SSE stream; only an explicit done event counts as success."""
    final: dict | None = None
    data_lines: list[str] = []
    def consume():
        nonlocal final
        if not data_lines:
            return
        payload = "\n".join(data_lines).strip()
        data_lines.clear()
        if not payload or payload == "[DONE]":
            return
        try:
            message = json.loads(payload)
        except ValueError as e:
            raise ASRError("invalid JSON event from ASR provider") from e
        if not isinstance(message, dict):
            raise ASRError("malformed provider event")
        kind = message.get("type", "")
        if kind == "error":
            raise ASRError("ASR provider returned error: " + str(message.get("message", "unknown"))[:300])
        if kind == "transcript.text.done":
            if not isinstance(message.get("text"), str):
                raise ASRError("ASR done event lacks text")
            final = {"text": message["text"], "usage": message.get("usage") or {}}
    for raw in lines:
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        line = line.strip("\r\n")
        if not line:
            consume()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())
    consume()
    if final is None:
        raise ASRError("ASR stream ended without transcript.text.done; do not consider it complete")
    return final


def build_payload(audio: bytes, file_suffix: str, *, language: str = "zh") -> dict:
    if language not in {"zh", "en"}:
        raise ASRError("language must be zh or en")
    fmt = SUPPORTED.get(file_suffix.lower())
    if fmt is None:
        raise ASRError("unsupported audio format; convert to MP3/WAV/OGG first")
    format_info = {"type": fmt, "rate": 16000, "bits": 16, "channel": 1}
    if fmt == "wav":
        format_info["codec"] = "pcm_s16le"
    return {"audio": {"data": base64.b64encode(audio).decode("ascii"),
                      "input": {"transcription": {"model": "stepaudio-2.5-asr",
                                                   "language": language, "enable_itn": True},
                                "format": format_info}}}


def _bytes_from_media(path: Path, *, ffmpeg: str = "ffmpeg") -> tuple[bytes, str]:
    suffix = path.suffix.lower()
    if suffix in SUPPORTED:
        return path.read_bytes(), suffix
    with tempfile.TemporaryDirectory(prefix="video-clips-asr-") as temp:
        output = Path(temp) / "audio.mp3"
        try:
            subprocess.run([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                            "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k",
                            str(output)], capture_output=True, check=True, timeout=240)
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            raise ASRError(f"could not extract audio using FFmpeg: {type(e).__name__}") from e
        return output.read_bytes(), ".mp3"


def transcribe(source: str | Path, output: str | Path, *, language: str = "zh",
               api_key: str | None = None, timeout: int = 240, ffmpeg: str = "ffmpeg") -> dict:
    """Explicit paid operation: one request at most, never silently retry or switch provider."""
    path = Path(source).expanduser().resolve(strict=True)
    dest = Path(output).expanduser().resolve()
    if not path.is_file() or not path.stat().st_size:
        raise ASRError("source audio is missing or empty")
    if not dest.parent.is_dir():
        raise ASRError("output parent directory missing")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if dest.exists():
        old = json.loads(dest.read_text(encoding="utf-8"))
        if old.get("source_sha256") == digest and old.get("provider") == "stepaudio-2.5-asr":
            return old  # no double billing for identical source
        raise ASRError("output exists with different source; choose a different output path")
    pending = dest.with_name(dest.name + ".pending.json")
    if pending.exists():
        raise ASRError(f"previous request may have been submitted; inspect {pending} before retrying")
    key = api_key or os.environ.get("STEPFUN_API_KEY") or os.environ.get("STEP_API_KEY")
    if not key:
        raise ASRError("missing STEPFUN_API_KEY or STEP_API_KEY (Normal API key)")
    audio, suffix = _bytes_from_media(path, ffmpeg=ffmpeg)
    if not audio or len(audio) > 30 * 1024 * 1024:
        raise ASRError("normalized audio must be between 1 byte and 30 MiB; split long media first")
    payload = build_payload(audio, suffix, language=language)
    request = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Authorization": f"Bearer {key}",
                                              "Content-Type": "application/json",
                                              "Accept": "text/event-stream"}, method="POST")
    # Persist the identity *before* submitting; ambiguous network failures must not be resubmitted.
    with pending.open("x", encoding="utf-8") as file:
        json.dump({"provider": "stepaudio-2.5-asr", "source_sha256": digest,
                   "status": "submission-uncertain", "billing": "unknown"}, file)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = parse_sse(response)
    except urllib.error.HTTPError as e:
        raise ASRError(f"ASR HTTP {e.code}; request state is preserved in pending file") from e
    except urllib.error.URLError as e:
        raise ASRError("ASR network failure; request state is preserved in pending file") from e
    except TimeoutError as e:
        raise ASRError("ASR timeout; request state is preserved in pending file") from e
    completed = {**result, "provider": "stepaudio-2.5-asr", "source_sha256": digest,
                 "language": language, "timestamps_available": False,
                 "billing": "unknown"}
    with dest.open("x", encoding="utf-8") as file:
        json.dump(completed, file, ensure_ascii=False, indent=2)
    pending.unlink()
    return completed
