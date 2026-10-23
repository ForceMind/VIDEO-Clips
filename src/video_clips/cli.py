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
from .timed_asr import captions_from_step_file
from .rough_cut import compile_rough_cut, video_metadata, read_cut_decisions
from .editorial import make_editorial_brief, approve_editorial_proposals
from .openverse import search_audio
from .jianying import export_plan, run_external, external_entry
from .yichen import route_asr, skill_entry
from .agent import AgentOptions, STRATEGIES
from .llm import ModelConfig
from .pipeline import run_agent_pipeline


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="video-clips", description="Local-first automated video editing toolkit")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="action", required=True)
    ui = sub.add_parser("ui", help="start a loopback-only local video editing application")
    ui.add_argument("--workspace", default=".", help="local media/job directory accessible to the UI")
    ui.add_argument("--port", type=int, default=8765)
    batch = sub.add_parser("batch-edit", help="run a sequential manifest of resumable Agent edits")
    batch.add_argument("manifest")
    batch.add_argument("--workdir", required=True)
    batch.add_argument("--allow-paid-model", action="store_true")
    batch.add_argument("--apply-ai-cuts", action="store_true")
    batch.add_argument("--render", action="store_true")
    batch.add_argument("--resume", action="store_true")
    agent = sub.add_parser("auto-edit", help="AI decisions → policy → timeline → optional FFmpeg MP4")
    agent.add_argument("source", help="local original video")
    agent_timings = agent.add_mutually_exclusive_group(required=True)
    agent_timings.add_argument("--srt", help="existing aligned transcript; no inferred timestamps")
    agent_timings.add_argument("--step-file", help="completed timestamp-bearing StepFun file-ASR result")
    agent.add_argument("--channel", type=int)
    agent.add_argument("--instruction", required=True)
    agent.add_argument("--strategy", choices=sorted(STRATEGIES), default="standard")
    agent.add_argument("--target-ms", type=int, help="advisory maximum duration; never overrides protections")
    agent.add_argument("--protect-term", action="append", default=[], help="retain cues containing this name/term")
    agent.add_argument("--apply-ai-cuts", action="store_true", help="apply only policy-permitted AI exclusions")
    provider = agent.add_mutually_exclusive_group(required=True)
    provider.add_argument("--model-endpoint", help="full Chat Completions compatible URL")
    provider.add_argument("--response", help="offline agent-decisions JSON instead of calling a model")
    agent.add_argument("--model", help="provider model ID")
    agent.add_argument("--key-env", default="VIDEO_CLIPS_MODEL_KEY")
    agent.add_argument("--max-tokens", type=int, default=16000)
    agent.add_argument("--model-timeout", type=int, default=180)
    agent.add_argument("--allow-paid-model", action="store_true", help="explicit opt-in to one model request")
    agent.add_argument("--workdir", required=True, help="new private local job directory")
    agent.add_argument("--resume", action="store_true", help="resume same inputs/settings without repeating cached model call")
    agent.add_argument("--render", action="store_true", help="render output.mp4 with FFmpeg locally")
    agent.add_argument("--aspect", choices=["source", "16:9", "9:16", "1:1"], default="source")
    agent.add_argument("--music", help="optional authorized local background audio")
    agent.add_argument("--music-volume", type=float, default=0.15)
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
    timed = sub.add_parser("step-file-srt", help="convert completed StepFun file-ASR utterance times to SRT (offline)")
    timed.add_argument("response", help="JSON response from StepFun /v1/audio/asr/file/query")
    timed.add_argument("--out", required=True)
    timed.add_argument("--channel", type=int, default=None, help="zero-based channel if multiple result streams")
    rough = sub.add_parser("rough-cut", help="compile timestamped speech into an auditable non-destructive edit plan")
    rough.add_argument("source", help="local original video (remains unchanged)")
    timings = rough.add_mutually_exclusive_group(required=True)
    timings.add_argument("--srt", help="existing time-aligned SRT subtitle file")
    timings.add_argument("--step-file", help="completed StepFun file-ASR JSON with utterance timestamps")
    rough.add_argument("--channel", type=int, help="zero-based StepFun channel when multichannel")
    rough.add_argument("--decisions", help="optional explicit reasoned 1-based cue exclusions JSON")
    rough.add_argument("--allow-numeric-exclusion", action="store_true")
    rough.add_argument("--padding-before-ms", type=int, default=120)
    rough.add_argument("--padding-after-ms", type=int, default=160)
    rough.add_argument("--merge-gap-ms", type=int, default=650)
    rough.add_argument("--out", required=True, help="new VIDEO-Clips edit plan JSON")
    rough.add_argument("--report", help="new human-readable JSON review report")
    brief = sub.add_parser("editorial-brief", help="generate a transcript-bound brief for AI editing (offline)")
    brief_timings = brief.add_mutually_exclusive_group(required=True)
    brief_timings.add_argument("--srt", help="timed subtitle input")
    brief_timings.add_argument("--step-file", help="completed StepFun file-ASR JSON")
    brief.add_argument("--channel", type=int, default=None)
    brief.add_argument("--context", type=int, default=1, help="number of neighboring cues, 0..3")
    brief.add_argument("--out", required=True, help="new editable JSON brief")
    approve = sub.add_parser("editorial-approve", help="compile reviewed AI proposals to safe rough-cut decisions")
    approve_timings = approve.add_mutually_exclusive_group(required=True)
    approve_timings.add_argument("--srt", help="same timed subtitle input as brief")
    approve_timings.add_argument("--step-file", help="same StepFun file-ASR JSON")
    approve.add_argument("--channel", type=int, default=None)
    approve.add_argument("--proposals", required=True, help="AI recommendations with explicit approved booleans")
    approve.add_argument("--allow-numeric-exclusion", action="store_true")
    approve.add_argument("--out", required=True, help="new reviewed cut-decisions JSON")
    approve.add_argument("--report", help="new audit report JSON (defaults to sibling)")
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


def _timed_cues(*, srt: str | None, step_file: str | None, channel: int | None):
    if srt:
        if channel is not None:
            raise PlanError("--channel applies only to StepFun file-ASR JSON")
        return parse_srt(Path(srt).expanduser().read_text(encoding="utf-8-sig"))
    payload = json.loads(Path(step_file).expanduser().read_text(encoding="utf-8"))
    return captions_from_step_file(payload, channel=channel)

def main(argv: list[str] | None = None) -> int:
    options = _parser().parse_args(argv)
    try:
        if options.action == "batch-edit":
            from .batch import run_batch
            result = run_batch(options.manifest, options.workdir, allow_paid=options.allow_paid_model,
                apply_cuts=options.apply_ai_cuts, render_output=options.render, resume=options.resume)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["state"] == "completed" else 2
        elif options.action == "ui":
            from .local_ui import serve
            serve(options.workspace, port=options.port)
        elif options.action == "auto-edit":
            if options.model_endpoint and not options.model:
                raise PlanError("--model-endpoint requires --model")
            if options.response and (options.model or options.allow_paid_model):
                raise PlanError("offline --response cannot be combined with --model or --allow-paid-model")
            cues = _timed_cues(srt=options.srt, step_file=options.step_file, channel=options.channel)
            config = (ModelConfig(options.model_endpoint, options.model, options.key_env,
                                  options.max_tokens, options.model_timeout) if options.model_endpoint else None)
            result = run_agent_pipeline(options.source, cues, options.workdir,
                AgentOptions(options.instruction, options.strategy, options.target_ms,
                             tuple(options.protect_term), options.apply_ai_cuts),
                model=config, response_file=options.response, allow_paid=options.allow_paid_model,
                render_output=options.render, aspect=options.aspect, resume=options.resume,
                music=options.music, music_volume=options.music_volume)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif options.action == "validate":
            plan = load_plan(options.plan)
            print(json.dumps({"name": plan.name, "duration_ms": plan.duration_ms,
                              "video_clips": len(plan.videos), "audio_clips": len(plan.audios),
                              "captions": len(plan.captions), "canvas": f"{plan.width}x{plan.height}@{plan.fps}"},
                             ensure_ascii=False, indent=2))
        elif options.action == "render":
            result = render(load_plan(options.plan), options.out, overwrite=options.overwrite)
            print(json.dumps({"output": str(result.path), "duration_s": result.duration_s,
                              "quality": result.quality}, indent=2))
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
        elif options.action == "step-file-srt":
            response = json.loads(Path(options.response).expanduser().read_text(encoding="utf-8"))
            captions = captions_from_step_file(response, channel=options.channel)
            target = Path(options.out).expanduser()
            if target.exists():
                raise FileExistsError(f"will not overwrite existing SRT: {target}")
            write_srt(captions, target)
            print(target)
        elif options.action == "editorial-brief":
            cues = _timed_cues(srt=options.srt, step_file=options.step_file, channel=options.channel)
            brief = make_editorial_brief(cues, context=options.context)
            _exclusive_write(options.out, json.dumps(brief, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps({"brief": options.out, "cues": len(cues),
                              "transcript_sha256": brief["transcript_sha256"]}, indent=2))
        elif options.action == "editorial-approve":
            cues = _timed_cues(srt=options.srt, step_file=options.step_file, channel=options.channel)
            raw = json.loads(Path(options.proposals).expanduser().read_text(encoding="utf-8"))
            decisions, audit = approve_editorial_proposals(
                cues, raw, allow_numeric_exclusion=options.allow_numeric_exclusion)
            target = Path(options.out).expanduser().resolve()
            report = (Path(options.report).expanduser().resolve() if options.report
                      else target.with_name(target.stem + ".review.json"))
            if target == report or target.exists() or report.exists():
                raise FileExistsError("decision/report files already exist or refer to same path")
            if not target.parent.is_dir() or not report.parent.is_dir():
                raise PlanError("decision/report output directories must already exist")
            _exclusive_write(str(target), json.dumps(decisions, ensure_ascii=False, indent=2) + "\n")
            _exclusive_write(str(report), json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps({"decisions": str(target), "review": str(report),
                              "approved_exclusions": audit["approved_exclusions"]}, indent=2))
        elif options.action == "rough-cut":
            if options.srt:
                if options.channel is not None:
                    raise PlanError("--channel applies only to StepFun file-ASR JSON")
                cues = parse_srt(Path(options.srt).expanduser().read_text(encoding="utf-8-sig"))
            else:
                payload = json.loads(Path(options.step_file).expanduser().read_text(encoding="utf-8"))
                cues = captions_from_step_file(payload, channel=options.channel)
            if options.decisions:
                raw = json.loads(Path(options.decisions).expanduser().read_text(encoding="utf-8"))
                excluded = read_cut_decisions(raw, len(cues))
            else:
                excluded = {}
            target = Path(options.out).expanduser().resolve()
            review = (Path(options.report).expanduser().resolve() if options.report
                      else target.with_name(target.stem + ".review.json"))
            if target.suffix.lower() != ".json" or review.suffix.lower() != ".json":
                raise PlanError("rough-cut output and review report must be JSON files")
            if target == review or target.exists() or review.exists():
                raise FileExistsError("output or review file already exists; use new filenames")
            if not target.parent.is_dir() or not review.parent.is_dir():
                raise PlanError("output directories must already exist")
            meta = video_metadata(options.source)
            plan, report = compile_rough_cut(options.source, cues, **meta,
                padding_before_ms=options.padding_before_ms,
                padding_after_ms=options.padding_after_ms,
                merge_gap_ms=options.merge_gap_ms,
                exclude=excluded, allow_numeric_exclusion=options.allow_numeric_exclusion)
            _exclusive_write(str(target), json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
            _exclusive_write(str(review), json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps({"plan": str(target), "review": str(review),
                              "original_ms": meta["duration_ms"],
                              "output_ms": report["output_duration_ms"],
                              "clips": len(plan["video"]), "captions": len(plan["captions"]),
                              "excluded_cues": len(report["excluded_cues"])}, ensure_ascii=False, indent=2))
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
