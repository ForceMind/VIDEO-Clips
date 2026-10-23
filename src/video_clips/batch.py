"""Sequential batch edits with persisted results and explicit paid/cut opt-ins."""
from __future__ import annotations

import math
from pathlib import Path

from .agent import AgentOptions, agent_request, strict_json
from .llm import ModelConfig, model_payload
from .pipeline import atomic_json, file_sha256, run_agent_pipeline
from .rough_cut import compile_rough_cut, video_metadata
from .subtitles import parse_srt
from .timed_asr import captions_from_step_file
from .quality import audio_duration_ms


def run_batch(manifest, workdir, *, allow_paid=False, apply_cuts=False, render_output=False, resume=False):
    source = Path(manifest).expanduser().resolve(strict=True)
    if source.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("batch manifest exceeds 4 MiB")
    payload = strict_json(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"schema", "jobs"} or payload["schema"] != "video-clips/batch/v1":
        raise ValueError("batch requires video-clips/batch/v1 schema and jobs only")
    records = payload["jobs"]
    if not isinstance(records, list) or not 1 <= len(records) <= 100:
        raise ValueError("batch must contain 1..100 jobs")
    def local(value):
        if not isinstance(value, str) or not value or "://" in value:
            raise ValueError("batch paths must be local filenames")
        path = Path(value).expanduser()
        return path if path.is_absolute() else source.parent / path
    prepared, names = [], set()
    fields = {"name", "source", "srt", "step_file", "channel", "instruction", "strategy", "target_ms",
              "protected_terms", "model", "response", "aspect", "music", "music_volume"}
    # Preflight the whole manifest before any model request or output directory creation.
    for row in records:
        if not isinstance(row, dict) or set(row) - fields:
            raise ValueError("batch job has unknown fields")
        name = row.get("name")
        if (not isinstance(name, str) or not 1 <= len(name) <= 64 or not name.isascii()
                or not all(c.isalnum() or c in "-_" for c in name) or name.casefold() in names
                or name.casefold() in {"con", "prn", "aux", "nul", *[f"com{i}" for i in range(1,10)], *[f"lpt{i}" for i in range(1,10)]}):
            raise ValueError("job names must be unique ASCII letters/digits/hyphens/underscores")
        names.add(name.casefold())
        media = local(row.get("source"))
        if bool(row.get("srt")) == bool(row.get("step_file")):
            raise ValueError("each batch job requires one srt or step_file transcript")
        if row.get("srt"):
            if row.get("channel") is not None: raise ValueError("channel only applies to Step file results")
            cues = parse_srt(local(row["srt"]).read_text(encoding="utf-8-sig"))
        else:
            cues = captions_from_step_file(strict_json(local(row["step_file"]).read_text(encoding="utf-8")), channel=row.get("channel"))
        if not isinstance(row.get("protected_terms", []), list): raise ValueError("protected_terms must be a list")
        options = AgentOptions(row.get("instruction", ""), row.get("strategy", "standard"),
                               row.get("target_ms"), tuple(row.get("protected_terms", [])), apply_cuts)
        request = agent_request(cues, options)
        compile_rough_cut(media, cues, **video_metadata(media))
        if bool(row.get("model")) == bool(row.get("response")):
            raise ValueError("each batch job requires exactly one model configuration or response file")
        config = None
        if row.get("model"):
            if not isinstance(row["model"], dict): raise ValueError("model configuration must be an object")
            try: config = ModelConfig(**row["model"])
            except TypeError as exc: raise ValueError("invalid model configuration fields") from exc
            model_payload(request, config)
        response = local(row["response"]) if row.get("response") else None
        if response: strict_json(response.read_text(encoding="utf-8"))
        if row.get("aspect", "source") not in {"source", "16:9", "9:16", "1:1"}:
            raise ValueError("invalid batch aspect ratio")
        volume = row.get("music_volume", .15)
        if type(volume) not in (int, float) or not math.isfinite(volume) or not 0 <= volume <= 2:
            raise ValueError("music_volume must be finite in 0..2")
        if row.get("music"):
            music = local(row["music"])
            if music.is_symlink(): raise ValueError("music cannot be a symlink")
            audio_duration_ms(music)
        prepared.append((row, media, cues, options, config, response))
    root = Path(workdir).expanduser()
    if root.is_symlink(): raise ValueError("batch directory cannot be a symlink")
    if resume and not root.is_dir(): raise FileNotFoundError("batch directory does not exist")
    if not resume: root.mkdir(parents=True, exist_ok=False)
    root = root.resolve()
    identity = {"manifest_sha256": file_sha256(source), "apply_cuts": apply_cuts, "render_output": render_output}
    report_path = root / "batch.json"
    if resume:
        previous = strict_json(report_path.read_text(encoding="utf-8"))
        if previous.get("identity") != identity: raise ValueError("batch manifest/settings changed; use a new directory")
    lock = root / ".batch-running"
    with lock.open("x", encoding="utf-8") as stream:
        stream.write("Confirm the previous batch worker has stopped before removing this lock.\n")
    report = {"schema": "video-clips/batch-result/v1", "identity": identity, "state": "running", "jobs": []}
    try:
        atomic_json(report_path, report)
        for row, media, cues, options, config, response in prepared:
            job_dir = root / row["name"]
            try:
                result = run_agent_pipeline(media, cues, job_dir, options, model=config,
                    response_file=response, allow_paid=allow_paid, render_output=render_output,
                    aspect=row.get("aspect", "source"), resume=resume and (job_dir / "job.json").is_file(),
                    music=local(row["music"]) if row.get("music") else None, music_volume=row.get("music_volume", .15))
                report["jobs"].append({"name": row["name"], "state": "completed", "result": result})
            except (OSError, ValueError, RuntimeError, TypeError) as exc:
                report["jobs"].append({"name": row["name"], "state": "failed", "error": str(exc)[:500]})
            atomic_json(report_path, report)
        report["state"] = "failed" if any(j["state"] == "failed" for j in report["jobs"]) else "completed"
        atomic_json(report_path, report)
        return report
    finally:
        lock.unlink(missing_ok=True)
