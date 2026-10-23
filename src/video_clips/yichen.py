"""Optional connection to a separately installed, licensed yichen-skills copy."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys


class SkillUnavailable(RuntimeError):
    pass


def skill_entry(skills_root: str | Path | None, skill: str, script: str) -> Path:
    root = skills_root or os.environ.get("YICHEN_SKILLS_ROOT")
    if not root:
        raise SkillUnavailable("YICHEN_SKILLS_ROOT is unset; obtain an authorized local checkout")
    root = Path(root).expanduser().resolve(strict=True)
    candidate = root / skill / "scripts" / script
    if not candidate.is_file():
        raise SkillUnavailable(f"missing external Skill entry: {candidate}")
    return candidate


def route_asr(*, skills_root: str | Path | None, provider: str = "auto",
              timestamps: bool = False, srt: bool = False) -> int:
    if provider not in {"auto", "step", "doubao"}:
        raise ValueError("invalid ASR provider")
    entry = skill_entry(skills_root, "yichen-asr", "route_asr.py")
    args = [sys.executable, str(entry), "--provider", provider]
    if timestamps:
        args.append("--need-timestamps")
    if srt:
        args.append("--need-srt")
    if not timestamps and not srt:
        args.append("--text-only")
    return subprocess.run(args, check=False, timeout=30).returncode
