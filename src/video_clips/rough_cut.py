"""Conservative speech-timed rough-cut compiler, without proprietary engines.

Only utterance timing or human-approved decisions are used. Untranscribed
regions may contain music or meaningful video; this is *not* silence detection.
The output is an editable VIDEO-Clips plan, never an in-place media edit.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import re
import subprocess
from collections.abc import Mapping, Sequence
from fractions import Fraction

from .plan import Caption, PlanError, parse_plan


class RoughCutError(PlanError):
    """Reject ambiguous or potentially destructive rough-cut requests."""


def video_metadata(source: str | Path, *, ffprobe: str = "ffprobe") -> dict:
    """Probe *local* video; no network access, no user media writes."""
    path = Path(source).expanduser()
    if path.is_symlink():
        raise RoughCutError("source cannot be a symlink")
    path = path.resolve(strict=True)
    if not path.is_file() or path.stat().st_size == 0:
        raise RoughCutError("source is not a nonempty regular file")
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height,avg_frame_rate,duration:format=duration", "-of", "json",
             str(path)], capture_output=True, text=True, check=True, timeout=45
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise RoughCutError("FFprobe could not inspect source video") from exc
    try:
        payload = json.loads(result.stdout)
        stream = payload["streams"][0]
        width = int(stream["width"])
        height = int(stream["height"])
        duration = float(stream.get("duration") or payload.get("format", {})["duration"])
        rate = Fraction(stream.get("avg_frame_rate", "30/1"))
        fps = max(1, min(60, round(float(rate))))
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError, OverflowError) as exc:
        raise RoughCutError("source has no usable video dimensions/duration/frame rate") from exc
    if not math.isfinite(duration) or duration <= 0 or duration > 21_600:
        raise RoughCutError("source duration must be 0..6 hours")
    if not 64 <= width <= 3840 or not 64 <= height <= 2160:
        raise RoughCutError("source dimensions are outside supported canvas limits")
    return {"duration_ms": int(duration * 1000), "width": width - width % 2,
            "height": height - height % 2, "fps": fps}


def read_cut_decisions(payload: object, cue_count: int) -> dict[int, str]:
    """1-based cue numbers, explicit reason required; no semantic inference."""
    if payload is None:
        return {}
    if not isinstance(payload, dict) or set(payload) != {"schema", "exclude"}:
        raise RoughCutError("decision file requires schema and exclude fields only")
    if payload["schema"] != "video-clips/cut-decisions/v1":
        raise RoughCutError("unsupported cut-decision schema")
    excluded = payload["exclude"]
    if not isinstance(excluded, list):
        raise RoughCutError("exclude must be a list")
    decisions: dict[int, str] = {}
    for record in excluded:
        if not isinstance(record, dict) or set(record) != {"cue", "reason"}:
            raise RoughCutError("each exclusion requires cue and reason")
        index, reason = record["cue"], record["reason"]
        if type(index) is not int or index < 1 or index > cue_count or index in decisions:
            raise RoughCutError("duplicate or out-of-range 1-based cue index")
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 200:
            raise RoughCutError("exclusion reason must be 1..200 characters")
        decisions[index] = reason.strip()
    return decisions


def _frame_ms(frame: int, fps: int) -> int:
    return round(frame * 1000 / fps)


def compile_rough_cut(
    source: str | Path,
    captions: Sequence[Caption],
    *,
    duration_ms: int,
    width: int,
    height: int,
    fps: int,
    padding_before_ms: int = 120,
    padding_after_ms: int = 160,
    merge_gap_ms: int = 650,
    exclude: Mapping[int, str] | None = None,
    allow_numeric_exclusion: bool = False,
) -> tuple[dict, dict]:
    """Build a gap-trimmed plan and an auditable decision report.

    Does not label gaps as acoustic silence; it removes *untranscribed* parts.
    The caller should listen and preview before accepting the plan.
    """
    source = Path(source).expanduser()
    if source.is_symlink():
        raise RoughCutError("source cannot be a symlink")
    source = source.resolve(strict=True)
    if not source.is_file():
        raise RoughCutError("source must be a regular local video file")
    if type(duration_ms) is not int or not 1 <= duration_ms <= 21_600_000:
        raise RoughCutError("duration_ms must be 1..21,600,000")
    if type(fps) is not int or not 1 <= fps <= 60:
        raise RoughCutError("fps must be 1..60")
    if type(width) is not int or type(height) is not int or not (64 <= width <= 3840 and 64 <= height <= 2160) or width % 2 or height % 2:
        raise RoughCutError("canvas dimensions must be supported even integers")
    if (type(padding_before_ms) is not int or type(padding_after_ms) is not int
        or type(merge_gap_ms) is not int or not (0 <= padding_before_ms <= 5000)
        or not (0 <= padding_after_ms <= 5000) or not (0 <= merge_gap_ms <= 10000)):
        raise RoughCutError("padding and merge gap options are out of range")
    if not captions or len(captions) > 1000:
        raise RoughCutError("1..1000 timed captions required")
    cues = list(captions)
    for i, cue in enumerate(cues):
        if not isinstance(cue, Caption) or not cue.text.strip() or not 0 <= cue.start_ms < cue.end_ms <= duration_ms:
            raise RoughCutError("cue is invalid or extends past source video duration")
        if i and cues[i-1].start_ms > cue.start_ms:
            raise RoughCutError("cues must appear in ascending time order")
        if i and cues[i-1].end_ms > cue.start_ms:
            raise RoughCutError("cue timestamps overlap; use one nonoverlapping channel")
    exclusions = dict(exclude or {})
    if any(type(i) is not int or i < 1 or i > len(cues) or not isinstance(reason, str) or not reason.strip()
           for i, reason in exclusions.items()):
        raise RoughCutError("invalid excluded cue numbers/reasons")
    for i in exclusions:
        if not allow_numeric_exclusion and re.search(r"\d|[零一二三四五六七八九十百千万亿]|[$¥￥%％]", cues[i-1].text):
            raise RoughCutError(f"cue {i} contains numerical content; explicit --allow-numeric-exclusion required")
    total_frames = math.floor(duration_ms * fps / 1000)
    if total_frames == 0:
        raise RoughCutError("source is too short for one output frame")
    active = [(i, cue) for i, cue in enumerate(cues, start=1) if i not in exclusions]
    if not active:
        raise RoughCutError("all utterances excluded: refusing to render empty video")
    # Expand before quantizing; no source interval crosses the checked media bounds.
    spans: list[list[int]] = []
    last_index: int | None = None
    for index, cue in active:
        start = max(0, cue.start_ms - padding_before_ms)
        end = min(duration_ms, cue.end_ms + padding_after_ms)
        # Never extend a retained cue into an explicitly excluded utterance.
        previous_excluded = [cues[k-1].end_ms for k in exclusions if k < index]
        next_excluded = [cues[k-1].start_ms for k in exclusions if k > index]
        start_frame = math.floor(start * fps / 1000)
        end_frame = min(total_frames, math.ceil(end * fps / 1000))
        if previous_excluded:
            start_frame = max(start_frame, math.ceil(max(previous_excluded) * fps / 1000))
        if next_excluded:
            end_frame = min(end_frame, math.floor(min(next_excluded) * fps / 1000))
        if end_frame <= start_frame:
            raise RoughCutError("utterance lands outside permitted full source frames")
        # An explicit removal must be honored; don't merge the clips around it.
        can_merge = last_index is not None and all(k not in exclusions for k in range(last_index+1, index))
        if spans and can_merge and _frame_ms(start_frame, fps) - _frame_ms(spans[-1][1], fps) <= merge_gap_ms:
            spans[-1][1] = max(spans[-1][1], end_frame)
        else:
            spans.append([start_frame, end_frame])
        last_index = index
    mapped: list[tuple[int, int, int]] = []   # original start,end, output start (milliseconds)
    clips: list[dict] = []
    cursor = 0
    for start_frame, end_frame in spans:
        start_ms, end_ms = _frame_ms(start_frame, fps), _frame_ms(end_frame, fps)
        length_ms = end_ms - start_ms
        if length_ms < 1:
            raise RoughCutError("frame quantization produced empty clip")
        clips.append({"source": str(source), "start_ms": cursor,
                      "source_start_ms": start_ms, "duration_ms": length_ms,
                      "speed": 1.0, "volume": 1.0})
        mapped.append((start_ms, end_ms, cursor))
        cursor += length_ms
    output_captions: list[dict] = []
    for index, cue in active:
        for src_start, src_end, dst_start in mapped:
            if src_start <= cue.start_ms and cue.end_ms <= src_end:
                output_captions.append({"text": cue.text, "start_ms": dst_start + cue.start_ms - src_start,
                                        "duration_ms": cue.duration_ms})
                break
        else:
            raise RoughCutError(f"cue {index} cannot be placed on output timeline")
    # Captions stay in order and do not overlap because ranges are disjoint and ordered.
    plan = {"schema": "video-clips/v1", "name": source.stem + " — rough cut",
            "canvas": {"width": width, "height": height, "fps": fps},
            "video": clips, "audio": [], "captions": output_captions}
    parse_plan(plan, base_path=source.parent)  # schema/overlap/media verification
    omitted = []
    cursor_source = 0
    for start_ms, end_ms, _ in mapped:
        if start_ms > cursor_source:
            omitted.append({"source_start_ms": cursor_source, "source_end_ms": start_ms,
                            "reason": "untranscribed interval; verify content before accepting cut"})
        cursor_source = end_ms
    if cursor_source < duration_ms:
        omitted.append({"source_start_ms": cursor_source, "source_end_ms": duration_ms,
                        "reason": "untranscribed interval; verify content before accepting cut"})
    report = {"schema": "video-clips/rough-cut-report/v1", "source": str(source),
              "source_duration_ms": duration_ms, "output_duration_ms": cursor,
              "included_cues": [i for i, _ in active],
              "excluded_cues": [{"cue": i, "text": cues[i-1].text, "reason": reason}
                                for i, reason in sorted(exclusions.items())],
              "kept_ranges": [{"source_start_ms": a, "source_end_ms": b,
                               "output_start_ms": dest} for a, b, dest in mapped],
              "removed_ranges": omitted, "warnings": [
                  "Untranscribed gaps are NOT confirmed silence and can include important video/audio.",
                  "This is a deterministic speech-timed rough cut, not AI semantic editing.",
                  "Preview video and listen to all cut boundaries before using the result."]}
    return plan, report
