"""Local FFmpeg renderer for a deterministic, linear A/V plan.

Does not use or distribute Jianying code/libraries. All subprocesses use argv,
never the shell. Outputs are verified after FFmpeg finishes successfully.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from .plan import Clip, Plan, PlanError
from .subtitles import write_srt


@dataclass(frozen=True)
class RenderResult:
    path: Path
    duration_s: float
    width: int
    height: int
    fps: int


def _run(args: list[str], *, timeout: int = 600) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, capture_output=True, text=True, check=True, timeout=timeout)
    except FileNotFoundError as e:
        raise RuntimeError(f"binary missing: {args[0]}") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"{args[0]} failed: {e.stderr[-4000:]}") from e


def has_audio(path: Path, ffprobe: str = "ffprobe") -> bool:
    result = _run([ffprobe, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                   "-of", "json", str(path)], timeout=40)
    return bool(json.loads(result.stdout).get("streams"))


def _tempo(speed: float) -> str:
    filters: list[str] = []
    while speed > 2:
        filters.append("atempo=2.0")
        speed /= 2
    while speed < 0.5:
        filters.append("atempo=0.5")
        speed *= 2
    filters.append(f"atempo={speed:.7f}")
    return ",".join(filters)


def _time(ms: int | float) -> str:
    return f"{ms / 1000:.6f}"


def build_command(plan: Plan, target: Path, scratch: Path, *, ffmpeg: str = "ffmpeg",
                  ffprobe: str = "ffprobe") -> list[str]:
    """Build FFmpeg command. Side effects: only writes temporary subtitles."""
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    all_clips = list(plan.videos) + list(plan.audios)
    input_ids: dict[Clip, int] = {}
    for clip in all_clips:
        # A repeated input is intentional because each timeline segment has a different trim.
        idx = len(input_ids)
        if clip in input_ids:
            # Same clip value can be shared by audio/video entries without sharing input options.
            idx = input_ids[clip]
        else:
            idx = len(input_ids)
            input_ids[clip] = idx
            if clip.kind == "video" and clip.path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
                cmd.extend(["-loop", "1", "-framerate", str(plan.fps)])
            cmd.extend(["-i", str(clip.path)])

    graph: list[str] = []
    vlabels: list[str] = []
    last = 0
    for n, clip in enumerate(plan.videos):
        if clip.start_ms > last:
            duration = clip.start_ms - last
            name = f"gap{n}"
            graph.append(f"color=c=black:s={plan.width}x{plan.height}:r={plan.fps}:d={_time(duration)},format=yuv420p[{name}]")
            vlabels.append(f"[{name}]")
        idx = input_ids[clip]
        start = _time(clip.source_start_ms)
        input_length = _time(clip.duration_ms * clip.speed)
        name = f"v{n}"
        graph.append(
            f"[{idx}:v]trim=start={start}:duration={input_length},"
            f"setpts=(PTS-STARTPTS)/{clip.speed:.7f},"
            f"fps={plan.fps},scale={plan.width}:{plan.height}:force_original_aspect_ratio=decrease,"
            f"pad={plan.width}:{plan.height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[{name}]"
        )
        vlabels.append(f"[{name}]")
        last = clip.end_ms
    if last < plan.duration_ms:
        tail = plan.duration_ms - last
        graph.append(f"color=c=black:s={plan.width}x{plan.height}:r={plan.fps}:d={_time(tail)},format=yuv420p[tail]")
        vlabels.append("[tail]")
    graph.append("".join(vlabels) + f"concat=n={len(vlabels)}:v=1:a=0[vbase]")
    if plan.captions:
        subtitle = write_srt(plan.captions, scratch / "captions.srt")
        # scratch is a tool-created temp directory; never interpolate user-provided text.
        escaped = str(subtitle).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        graph.append(f"[vbase]subtitles=filename='{escaped}'[vout]")
    else:
        graph.append("[vbase]null[vout]")

    graph.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={_time(plan.duration_ms)},asetpts=PTS-STARTPTS[asilence]")
    alabels = ["[asilence]"]
    for i, clip in enumerate(all_clips):
        if clip.volume == 0:
            continue
        if clip.kind == "video" and clip.path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
            continue
        if not has_audio(clip.path, ffprobe):
            if clip.kind == "audio":
                raise PlanError(f"audio track has no audio stream: {clip.path}")
            continue
        idx = input_ids[clip]
        label = f"a{i}"
        length = _time(clip.duration_ms * clip.speed)
        graph.append(
            f"[{idx}:a]atrim=start={_time(clip.source_start_ms)}:duration={length},"
            f"asetpts=PTS-STARTPTS,{_tempo(clip.speed)},volume={clip.volume:.7f},"
            f"aresample=48000,aformat=channel_layouts=stereo,"
            f"adelay={clip.start_ms}:all=1[{label}]"
        )
        alabels.append(f"[{label}]")
    graph.append("".join(alabels) + f"amix=inputs={len(alabels)}:duration=longest:normalize=0,"
                 f"atrim=duration={_time(plan.duration_ms)},asetpts=PTS-STARTPTS[aout]")
    cmd.extend(["-filter_complex", ";".join(graph), "-map", "[vout]", "-map", "[aout]",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(plan.fps),
                "-c:a", "aac", "-ar", "48000", "-movflags", "+faststart", str(target)])
    return cmd


def render(plan: Plan, output: str | Path, *, overwrite: bool = False,
           ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe", timeout: int = 600) -> RenderResult:
    if shutil.which(ffmpeg) is None or shutil.which(ffprobe) is None:
        raise RuntimeError("FFmpeg and FFprobe must be installed and available in PATH")
    target = Path(output).expanduser().resolve()
    if target.suffix.lower() != ".mp4":
        raise PlanError("output must end in .mp4")
    if target.exists() and not overwrite:
        raise FileExistsError(f"output exists, use --overwrite explicitly: {target}")
    if not target.parent.is_dir():
        raise PlanError("output directory must already exist")
    with tempfile.TemporaryDirectory(prefix="video-clips-") as work:
        scratch = Path(work)
        staged = scratch / "render.mp4"
        cmd = build_command(plan, staged, scratch, ffmpeg=ffmpeg, ffprobe=ffprobe)
        _run(cmd, timeout=timeout)
        if not staged.is_file() or staged.stat().st_size == 0:
            raise RuntimeError("renderer did not create nonempty MP4")
        metadata = _run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                         "-of", "json", str(staged)], timeout=40)
        duration = float(json.loads(metadata.stdout)["format"]["duration"])
        if abs(duration - plan.duration_ms / 1000) > max(0.25, 2 / plan.fps):
            raise RuntimeError(f"output duration mismatch: {duration} sec")
        # Avoid replacing user files without explicit overwrite. Stage on same directory
        # for atomic rename and copy the checked artifact after validation.
        if target.exists() and not overwrite:
            raise FileExistsError(f"output appeared during render: {target}")
        if not overwrite:
            with target.open("xb") as stream, staged.open("rb") as source:
                shutil.copyfileobj(source, stream)
        else:
            import os
            import uuid
            temporary_target = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
            try:
                shutil.copyfile(staged, temporary_target)
                os.replace(temporary_target, target)
            finally:
                temporary_target.unlink(missing_ok=True)
    return RenderResult(target, duration, plan.width, plan.height, plan.fps)
