"""An intentionally vendor-neutral, validated timeline schema."""
from __future__ import annotations
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any


class PlanError(ValueError):
    """Invalid edit plan; no rendering should be attempted."""


def _obj(value: Any, name: str) -> dict:
    if not isinstance(value, dict):
        raise PlanError(f"{name} must be an object")
    return value


def _int(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise PlanError(f"{name} must be an integer between {low} and {high}")
    return value


def _float(value: Any, name: str, low: float, high: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise PlanError(f"{name} must be a finite number between {low} and {high}")
    return float(value)


def _keys(value: dict, allowed: set[str], name: str) -> None:
    extra = set(value) - allowed
    if extra:
        raise PlanError(f"{name} has unknown keys: {sorted(extra)}")


@dataclass(frozen=True)
class Clip:
    path: Path
    start_ms: int
    source_start_ms: int
    duration_ms: int
    speed: float
    volume: float
    kind: str

    @property
    def end_ms(self) -> int:
        return self.start_ms + self.duration_ms


@dataclass(frozen=True)
class Caption:
    text: str
    start_ms: int
    duration_ms: int

    @property
    def end_ms(self) -> int:
        return self.start_ms + self.duration_ms


@dataclass(frozen=True)
class Plan:
    name: str
    width: int
    height: int
    fps: int
    videos: tuple[Clip, ...]
    audios: tuple[Clip, ...]
    captions: tuple[Caption, ...]
    base_path: Path

    @property
    def duration_ms(self) -> int:
        return max([c.end_ms for c in (*self.videos, *self.audios, *self.captions)])


def parse_plan(value: dict, *, base_path: Path) -> Plan:
    value = _obj(value, "plan")
    _keys(value, {"schema", "name", "canvas", "video", "audio", "captions"}, "plan")
    if value.get("schema") != "video-clips/v1":
        raise PlanError("schema must be video-clips/v1")
    name = value.get("name", "Untitled")
    if not isinstance(name, str) or not 1 <= len(name) <= 128:
        raise PlanError("name must be 1..128 characters")
    canvas = _obj(value.get("canvas"), "canvas")
    _keys(canvas, {"width", "height", "fps"}, "canvas")
    width = _int(canvas.get("width"), "canvas.width", 64, 3840)
    height = _int(canvas.get("height"), "canvas.height", 64, 2160)
    fps = _int(canvas.get("fps"), "canvas.fps", 1, 60)
    if width % 2 or height % 2:
        raise PlanError("canvas dimensions must be even for H.264 yuv420p")

    def clips(field: str) -> tuple[Clip, ...]:
        entries = value.get(field, [])
        if not isinstance(entries, list):
            raise PlanError(f"{field} must be a list")
        if len(entries) > 256:
            raise PlanError(f"too many {field} clips")
        result: list[Clip] = []
        for index, raw in enumerate(entries):
            label = f"{field}[{index}]"
            raw = _obj(raw, label)
            _keys(raw, {"source", "start_ms", "source_start_ms", "duration_ms", "speed", "volume"}, label)
            source = raw.get("source")
            if not isinstance(source, str) or not source or "\0" in source or "://" in source:
                raise PlanError(f"{label}.source must be a local filename")
            path = Path(source).expanduser()
            if not path.is_absolute():
                path = base_path / path
            if path.is_symlink():
                raise PlanError(f"{label}.source cannot be a symlink: {path}")
            path = path.resolve()
            if not path.is_file() or path.stat().st_size == 0:
                raise PlanError(f"{label}.source is missing/empty/not a regular file: {path}")
            result.append(Clip(
                path=path,
                start_ms=_int(raw.get("start_ms", 0), label + ".start_ms", 0, 21_600_000),
                source_start_ms=_int(raw.get("source_start_ms", 0), label + ".source_start_ms", 0, 21_600_000),
                duration_ms=_int(raw.get("duration_ms"), label + ".duration_ms", 1, 21_600_000),
                speed=_float(raw.get("speed", 1), label + ".speed", 0.25, 4.0),
                volume=_float(raw.get("volume", 1), label + ".volume", 0, 2),
                kind=field,
            ))
        return tuple(sorted(result, key=lambda c: c.start_ms))

    videos, audios = clips("video"), clips("audio")
    if not videos:
        raise PlanError("at least one primary video clip is required")
    for previous, following in zip(videos, videos[1:]):
        if previous.end_ms > following.start_ms:
            raise PlanError("primary video segments overlap; use audio tracks for overlapping sound")

    raw_captions = value.get("captions", [])
    if not isinstance(raw_captions, list) or len(raw_captions) > 1000:
        raise PlanError("captions must be a list of at most 1000 entries")
    captions: list[Caption] = []
    for i, raw in enumerate(raw_captions):
        label = f"captions[{i}]"
        raw = _obj(raw, label)
        _keys(raw, {"text", "start_ms", "duration_ms"}, label)
        txt = raw.get("text")
        if not isinstance(txt, str) or not txt.strip() or len(txt) > 500:
            raise PlanError(f"{label}.text must contain 1..500 characters")
        captions.append(Caption(
            txt,
            _int(raw.get("start_ms"), label + ".start_ms", 0, 21_600_000),
            _int(raw.get("duration_ms"), label + ".duration_ms", 1, 21_600_000),
        ))
    captions = sorted(captions, key=lambda c: c.start_ms)
    for previous, following in zip(captions, captions[1:]):
        if previous.end_ms > following.start_ms:
            raise PlanError("captions overlap; resolve the timing before rendering")
    plan = Plan(name, width, height, fps, videos, audios, tuple(captions), base_path)
    if plan.duration_ms > 21_600_000:
        raise PlanError("plans longer than six hours are not supported")
    return plan


def load_plan(path: str | Path) -> Plan:
    source = Path(path).expanduser().resolve(strict=True)
    def pairs(items):
        obj = {}
        for key, val in items:
            if key in obj:
                raise PlanError(f"duplicate JSON key: {key}")
            obj[key] = val
        return obj
    try:
        value = json.loads(source.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                           parse_constant=lambda s: (_ for _ in ()).throw(PlanError(f"invalid constant: {s}")))
    except json.JSONDecodeError as e:
        raise PlanError(f"invalid JSON: {e}") from e
    return parse_plan(value, base_path=source.parent)
