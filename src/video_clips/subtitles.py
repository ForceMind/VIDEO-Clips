"""SRT handling used by the FFmpeg renderer and the editable timeline."""
from __future__ import annotations
import re
from pathlib import Path
from .plan import Caption, PlanError


def _srt_time(ms: int) -> str:
    hours, remain = divmod(ms, 3_600_000)
    minutes, remain = divmod(remain, 60_000)
    seconds, millis = divmod(remain, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def write_srt(captions: tuple[Caption, ...] | list[Caption], path: str | Path) -> Path:
    p = Path(path)
    lines = []
    for idx, caption in enumerate(captions, start=1):
        lines.extend([str(idx), f"{_srt_time(caption.start_ms)} --> {_srt_time(caption.end_ms)}",
                      caption.text, ""])
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def parse_srt(text: str) -> list[Caption]:
    marker = re.compile(r"^(\d\d):(\d\d):(\d\d)[,.](\d{3})$")
    captions: list[Caption] = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        lines = [line for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        if lines[0].strip().isdigit():
            lines = lines[1:]
        if len(lines) < 2 or " --> " not in lines[0]:
            raise PlanError("invalid SRT cue")
        raw_start, raw_end = lines[0].split(" --> ", 1)
        def ms(s: str) -> int:
            match = marker.fullmatch(s.strip())
            if not match:
                raise PlanError(f"invalid SRT timestamp: {s}")
            h, m, sec, frac = map(int, match.groups())
            if m > 59 or sec > 59:
                raise PlanError("SRT minute or second out of range")
            return (h * 3600 + m * 60 + sec) * 1000 + frac
        start, end = ms(raw_start), ms(raw_end)
        if start >= end:
            raise PlanError("non-positive SRT cue duration")
        captions.append(Caption("\n".join(lines[1:]), start, end - start))
    return captions
