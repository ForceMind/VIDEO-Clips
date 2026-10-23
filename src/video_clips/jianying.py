"""Optional, out-of-tree Jianying adapter; does not redistribute restricted code."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
from .plan import Plan


class AdapterError(RuntimeError):
    pass


def external_entry(root: str | Path | None = None) -> Path:
    raw = root or os.environ.get("JIANYING_HEADLESS_ROOT")
    if not raw:
        raise AdapterError("JIANYING_HEADLESS_ROOT is unset; obtain an authorized local checkout")
    candidate = Path(raw).expanduser().resolve(strict=True)
    marker = candidate / "project.json"
    entry = candidate / "skills" / "yichen-jianying-edit" / "scripts" / "headless_draft.py"
    if not marker.is_file() or not entry.is_file():
        raise AdapterError("external checkout is missing project.json or Skill entrypoint")
    meta = json.loads(marker.read_text(encoding="utf-8"))
    if meta.get("id") != "jianying-headless":
        raise AdapterError("external directory is not a recognized Jianying Headless checkout")
    return entry


def run_external(args: list[str], *, root: str | Path | None = None, timeout: int = 300) -> int:
    entry = external_entry(root)
    env = dict(os.environ)
    env["JIANYING_HEADLESS_ROOT"] = str(entry.parents[3])
    completed = subprocess.run([sys.executable, str(entry), *args], check=False, env=env, timeout=timeout)
    return completed.returncode


def export_plan(plan: Plan, output: str | Path) -> Path:
    """Convert the supported simple timeline subset to Jy native plan schema.

    Not a compatibility guarantee: native version/hash gates still apply.
    """
    output = Path(output).expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"will not overwrite native plan: {output}")
    tracks = []
    for clips, kind, name in [(plan.videos, "video", "主视频"), (plan.audios, "audio", "独立音轨")]:
        if not clips:
            continue
        segments = []
        for c in clips:
            segments.append({"source": str(c.path), "start_us": c.start_ms * 1000,
                             "duration_us": c.duration_ms * 1000,
                             "source_start_us": c.source_start_ms * 1000,
                             "source_duration_us": round(c.duration_ms * c.speed * 1000),
                             "speed": c.speed, "volume": c.volume})
        tracks.append({"type": kind, "name": name, "segments": segments})
    if plan.captions:
        tracks.append({"type": "text", "name": "字幕", "segments": [
            {"text": c.text, "start_us": c.start_ms * 1000, "duration_us": c.duration_ms * 1000,
             "size": 6, "x": 0, "y": -0.78, "color": "#FFFFFF",
             "border_color": "#000000", "border_width": 0.05} for c in plan.captions
        ]})
    result = {"schema": "jy14-headless-plan/v1", "name": plan.name,
              "canvas": {"width": plan.width, "height": plan.height, "fps": plan.fps},
              "tracks": tracks}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return output
