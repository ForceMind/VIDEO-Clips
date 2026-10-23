"""Command-line entrypoint: each paid/network operation is explicit."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
from . import __version__
from .plan import load_plan, PlanError
from .render import render
from .subtitles import write_srt, parse_srt
from .step_asr import transcribe
from .openverse import search_audio
from .jianying import export_plan, run_external, external_entry
from .yichen import route_asr, skill_entry


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="video-clips", description="Local-first automated video editing toolkit")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="action", required=True)
    validate = sub.add_parser("validate", help="validate the vendor-neutral edit plan")
    validate.add_argument("plan")
    render_ = sub.add_parser("render", help="render local MP4 with FFmpeg")
    render_.add_argument("plan")
    render_.add_argument("--out", required=True)
    render_.add_argument("--overwrite", action="store_true")
    caption = sub.add_parser("captions", help="export timed plan captions to SRT")
    caption.add_argument("plan")
    caption.add_argument("--out", required=True)
    import_ = sub.add_parser("import-srt", help="write a new plan populated from SRT")
    import_.add_argument("plan")
    import_.add_argument("--srt", required=True)
    import_.add_argument("--out", required=True)
    doctor = sub.add_parser("doctor", help="show dependencies without calling paid services")
    doctor.add_argument("--jianying-root")
    doctor.add_argument("--skills-root")
    asr = sub.add_parser("step-asr", help="explicitly submit local media to paid StepAudio 2.5 ASR")
    asr.add_argument("source")
    asr.add_argument("--out", required=True)
    asr.add_argument("--language", choices=["zh", "en"], default="zh")
    sound = sub.add_parser("openverse", help="search Openverse audio metadata")
    sound.add_argument("query")
    sound.add_argument("--commercial", action="store_true")
    sound.add_argument("--limit", type=int, default=10)
    jyplan = sub.add_parser("jianying-plan", help="convert supported plan subset to external Jianying schema")
    jyplan.add_argument("plan")
    jyplan.add_argument("--out", required=True)
    jy = sub.add_parser("jianying", help="invoke a separately installed Jianying Headless checkout")
    jy.add_argument("command", choices=["doctor", "build", "verify-build"])
    jy.add_argument("--root")
    jy.add_argument("--plan")
    jy.add_argument("--out")
    jy.add_argument("--build")
    yr = sub.add_parser("yichen-route-asr", help="call locally installed yichen-asr router (no submission)")
    yr.add_argument("--skills-root")
    yr.add_argument("--provider", choices=["auto", "step", "doubao"], default="auto")
    yr.add_argument("--timestamps", action="store_true")
    yr.add_argument("--srt", action="store_true")
    return parser


def _exclusive_write(path: str, content: str) -> None:
    with Path(path).expanduser().open("x", encoding="utf-8") as f:
        f.write(content)


def _doctor(jianying_root: str | None, skills_root: str | None) -> dict:
    def available(call):
        try:
            call()
            return True
        except (OSError, RuntimeError, ValueError):
            return False
    return {"version": __version__, "ffmpeg": shutil.which("ffmpeg") is not None,
            "ffprobe": shutil.which("ffprobe") is not None,
            "stepfun_key_configured": bool(os.environ.get("STEPFUN_API_KEY") or os.environ.get("STEP_API_KEY")),
            "jianying_checkout_detected": available(lambda: external_entry(jianying_root)),
            "yichen_asr_router_detected": available(lambda: skill_entry(skills_root, "yichen-asr", "route_asr.py"))}


def main(argv: list[str] | None = None) -> int:
    options = _parser().parse_args(argv)
    try:
        if options.action == "validate":
            plan = load_plan(options.plan)
            print(json.dumps({"name": plan.name, "duration_ms": plan.duration_ms,
                              "video_clips": len(plan.videos), "audio_clips": len(plan.audios),
                              "captions": len(plan.captions), "canvas": f"{plan.width}x{plan.height}@{plan.fps}"},
                             ensure_ascii=False, indent=2))
        elif options.action == "render":
            result = render(load_plan(options.plan), options.out, overwrite=options.overwrite)
            print(json.dumps({"output": str(result.path), "duration_s": result.duration_s}, indent=2))
        elif options.action == "captions":
            plan = load_plan(options.plan)
            if not plan.captions:
                raise PlanError("plan has no captions")
            destination = Path(options.out).expanduser()
            if destination.exists():
                raise FileExistsError(destination)
            write_srt(plan.captions, destination)
            print(destination)
        elif options.action == "import-srt":
            # Write a new plan, don't modify the source. Resolve source paths before relocation.
            plan = load_plan(options.plan)
            base = Path(options.plan).expanduser().resolve()
            payload = json.loads(base.read_text(encoding="utf-8"))
            for kind in ("video", "audio"):
                for raw in payload.get(kind, []):
                    source = Path(raw["source"]).expanduser()
                    raw["source"] = str((base.parent / source).resolve() if not source.is_absolute()
                                        else source.resolve())
            payload["captions"] = [{"text": c.text, "start_ms": c.start_ms,
                                    "duration_ms": c.duration_ms} for c in parse_srt(
                                        Path(options.srt).read_text(encoding="utf-8-sig"))]
            _exclusive_write(options.out, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            # Validate new artifact too.
            load_plan(options.out)
            print(options.out)
        elif options.action == "doctor":
            print(json.dumps(_doctor(options.jianying_root, options.skills_root), indent=2))
        elif options.action == "step-asr":
            print(json.dumps(transcribe(options.source, options.out, language=options.language),
                             ensure_ascii=False, indent=2))
        elif options.action == "openverse":
            print(json.dumps(search_audio(options.query, limit=options.limit,
                                          commercial=options.commercial), ensure_ascii=False, indent=2))
        elif options.action == "jianying-plan":
            print(export_plan(load_plan(options.plan), options.out))
        elif options.action == "jianying":
            if options.command == "doctor":
                return run_external(["doctor"], root=options.root, timeout=30)
            if options.command == "build":
                if not options.plan or not options.out:
                    raise PlanError("jianying build requires --plan and --out")
                return run_external(["build", "--plan", options.plan, "--out", options.out],
                                    root=options.root)
            if not options.build:
                raise PlanError("jianying verify-build requires --build")
            return run_external(["verify-build", "--build", options.build], root=options.root)
        elif options.action == "yichen-route-asr":
            return route_asr(skills_root=options.skills_root, provider=options.provider,
                             timestamps=options.timestamps, srt=options.srt)
        return 0
    except (PlanError, OSError, ValueError, RuntimeError) as error:
        print(f"video-clips: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
