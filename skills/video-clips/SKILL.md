---
name: video-clips
description: Edit local videos with VIDEO-Clips using aligned transcripts, explainable AI cue decisions, protected semantic cuts, SRT captions, optional local music and verified FFmpeg MP4. Use for speech rough cuts, highlights, reviewing or restoring AI exclusions, resumable edits and external Jianying plan handoff. Do not claim that text-only ASR provides timestamps or that FFmpeg output is a native Jianying export.
---

# VIDEO-Clips

Use the installed independent Python toolkit. Keep original media unchanged and place each edit in a new private job directory.

1. Run `python -m video_clips doctor`. Require FFmpeg/FFprobe for media validation/rendering. Install this repository's Python package if the module is absent; do not install a different similarly named package from a registry.
2. Obtain the video, natural-language objective and a genuinely aligned SRT or completed Step file-ASR result. Read [CLI and response contract](references/cli.md) for commands and recovery. Do not guess speech times. If only text is available, report the missing alignment and complete independent preparation work.
3. Select conservative/standard/aggressive/highlights. Protect named products with `--protect-term`. Treat target duration as advisory. Keep context and qualifiers. Do not promise subjective cut quality from structural checks.
4. Use an existing Agent reply via `--response` when supplied. Otherwise configure the user's chosen compatible endpoint/model, read a key from its environment variable and make a model call only when the user has authorized the applicable service/cost. Pass `--allow-paid-model` only within that authorization. Never log, commit or ask for a key in public code.
5. Run `auto-edit` with `--render`. Add `--apply-ai-cuts` only when automatic application is authorized; otherwise keep all semantic exclusions pending. The speech rough-cut still trims untranscribed regions, which can contain valuable visuals/audio. Do not call those regions confirmed silence.
6. Read `review.json`, `plan.json`, `quality.json` and `job.json`. Check applied/blocked decisions, retained names/numbers, target result, frame/decode checks and output hash. Report actual limitations and any unmet target.
7. For human approval, use `proposals.json` with `editorial-approve`, then compile `rough-cut` and render to a new filename. Restore excluded cues by removing their exclusions before compilation. For a visual, versioned workflow start `python -m video_clips ui --workspace /path/to/media`; keep the printed loopback session URL private.
8. Resume only identical source/transcript/options with `--resume`. Reuse cached model responses. Inspect uncertain-submission markers and provider billing before any paid retry; never silently clear them. Confirm a crashed worker has stopped before removing `.running`.
9. Export `jianying-plan` only as an external engine adapter plan. Native draft build/export requires a separately installed authorized checkout and compatible native environment. Preserve third-party licenses; do not vendor restricted source or paid media.

Return source/output paths, applied cut count, target result, quality evidence and unresolved constraints. Describe offline fixtures as fixture replay, not an actual model/ASR quality test. Do not deploy a hosted site or access the user's native computer to complete this workflow unless separately authorized.
