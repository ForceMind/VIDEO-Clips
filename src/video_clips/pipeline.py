"""Resumable local Agent → policy → timeline → subtitles → MP4 workflow."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import tempfile

from .agent import AgentOptions, agent_request, compile_agent_decisions, strict_json
from .editorial import transcript_sha256
from .llm import ModelConfig, complete
from .plan import parse_plan
from .render import render
from .rough_cut import compile_rough_cut, read_cut_decisions, video_metadata
from .subtitles import write_srt


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict):
    descriptor, name = tempfile.mkstemp(prefix=".write-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def run_agent_pipeline(source, captions, workdir, options: AgentOptions, *,
                       model: ModelConfig | None = None, response_file=None,
                       allow_paid: bool = False, render_output: bool = False,
                       aspect: str = "source", resume: bool = False) -> dict:
    options.validate()
    if aspect not in {"source", "16:9", "9:16", "1:1"}:
        raise ValueError("unsupported aspect ratio")
    source = Path(source).expanduser()
    if source.is_symlink():
        raise ValueError("source cannot be a symlink")
    source = source.resolve(strict=True)
    metadata = video_metadata(source)
    # Validate transcript AND compile feasibility before any potentially paid call.
    digest = transcript_sha256(captions)
    compile_rough_cut(source, captions, **metadata)
    if (model is None) == (response_file is None):
        raise ValueError("choose exactly one model configuration or offline response file")
    response_text = None
    if response_file is not None:
        response_text = Path(response_file).expanduser().read_text(encoding="utf-8")
        strict_json(response_text)
    if model:
        model.validate()
    identity = {"source": str(source), "source_sha256": file_sha256(source),
                "transcript_sha256": digest, "options": asdict(options), "aspect": aspect,
                "model": asdict(model) if model else None,
                "offline_response_sha256": hashlib.sha256(response_text.encode()).hexdigest() if response_text else None}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    root = Path(workdir).expanduser()
    if root.is_symlink():
        raise ValueError("job directory cannot be a symlink")
    if root.exists() and not resume:
        raise FileExistsError("job directory exists; choose a new directory or use --resume")
    if not root.exists() and resume:
        raise FileNotFoundError("cannot resume a missing job directory")
    if not root.exists():
        root.mkdir(parents=True, exist_ok=False)
    root = root.resolve()
    lock = root / ".running"
    with lock.open("x", encoding="utf-8") as stream:
        json.dump({"pid": os.getpid(), "note": "Remove only after confirming worker has stopped."}, stream)
    state_path = root / "job.json"
    state = None
    try:
        if state_path.exists():
            previous = strict_json(state_path.read_text(encoding="utf-8"))
            if previous.get("fingerprint") != fingerprint:
                raise ValueError("job inputs/settings changed; start a new job directory")
        elif resume:
            raise ValueError("job manifest missing; cannot safely resume")
        state = {"schema": "video-clips/job/v1", "fingerprint": fingerprint,
                 "identity": identity, "stage": "prepared"}
        atomic_json(state_path, state)
        request = agent_request(captions, options)
        atomic_json(root / "request.json", request)
        state["stage"] = "model"
        atomic_json(state_path, state)
        if response_text is not None:
            response = strict_json(response_text)
        else:
            response = complete(request, model, root, allow_paid=allow_paid)["response"]
        # Save even invalid semantic replies for inspection without another billable request.
        atomic_json(root / "agent-response.json", response)
        decisions, proposals, review = compile_agent_decisions(captions, response, options)
        excluded = read_cut_decisions(decisions, len(captions))
        plan, cut_report = compile_rough_cut(source, captions, **metadata, exclude=excluded)
        if aspect != "source":
            width, height = {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (1080, 1080)}[aspect]
            plan["canvas"].update(width=width, height=height)
        parsed_plan = parse_plan(plan, base_path=root)
        review["rough_cut"] = cut_report
        review["actual_duration_ms"] = parsed_plan.duration_ms
        review["target_met"] = None if options.target_ms is None else parsed_plan.duration_ms <= options.target_ms
        if review["target_met"] is False:
            review["warnings"].append("Target duration not achieved; protected content was preserved. Review settings/cues.")
        for name, data in (("decisions.json", decisions), ("proposals.json", proposals),
                           ("review.json", review), ("plan.json", plan)):
            atomic_json(root / name, data)
        write_srt(parsed_plan.captions, root / "captions.srt")
        state["stage"] = "planned"
        atomic_json(state_path, state)
        output = root / "output.mp4"
        if render_output:
            state["stage"] = "rendering"
            atomic_json(state_path, state)
            # Rendering is local and repeatable. Only replace this job's derived output.
            result = render(parsed_plan, output, overwrite=resume)
            state["output_sha256"] = file_sha256(result.path)
            state["stage"] = "completed"
            atomic_json(state_path, state)
        return {"workdir": str(root), "stage": state["stage"], "plan": str(root / "plan.json"),
                "review": str(root / "review.json"), "applied_cuts": len(excluded),
                "duration_ms": parsed_plan.duration_ms, "target_met": review["target_met"],
                "output": str(output) if render_output else None}
    except Exception as exc:
        if state is not None:
            state.update(stage="failed", error_type=type(exc).__name__)
            atomic_json(state_path, state)
        raise
    finally:
        lock.unlink(missing_ok=True)
