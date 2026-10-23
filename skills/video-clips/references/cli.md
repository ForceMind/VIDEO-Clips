# CLI and Agent reply contract

Run `python -m video_clips auto-edit --help` for the installed version's complete flags.

```bash
python -m video_clips auto-edit source.mp4 --srt source.srt \
  --instruction "Remove hesitations, preserve context and key numbers" \
  --strategy standard --protect-term VIDEO-Clips --target-ms 180000 \
  --response existing-agent-decisions.json --apply-ai-cuts \
  --workdir work/reviewed-edit --render
```

Replace `--srt` with `--step-file completed-file-asr.json` when available. Select a channel explicitly for multichannel imports. Text-only Step SSE does not establish timestamps. Automatic file-ASR submission/polling is not implemented in this version.

For an authorized compatible model request, replace `--response` with `--model-endpoint FULL_CHAT_COMPLETIONS_URL --model MODEL_ID --allow-paid-model`. Read the secret from `VIDEO_CLIPS_MODEL_KEY` or a named `--key-env`. Local HTTP endpoints must use loopback; remote endpoints must use HTTPS. Requests never follow redirects. A model must support JSON object responses and the configured token budget.

Add `--aspect 9:16` (or `16:9`, `1:1`) for fit-and-pad conversion; this is not face tracking. Add `--music /local/authorized/audio.mp3 --music-volume 0.15` to mix one local bed, trimmed to the output duration or source audio length. There is no automatic licensed audio search/download/looping/ducking in this version.

## Offline response

Use `editorial-brief --srt source.srt --out brief.json` to get the transcript fingerprint and cue records. Emit:

```json
{
  "schema": "video-clips/agent-decisions/v1",
  "transcript_sha256": "fingerprint from the same transcript",
  "decisions": [
    {"cue": 1, "text": "exact original cue text", "action": "KEEP",
     "reason": "Key argument", "category": "important", "confidence": 0.99,
     "duplicate_of": null}
  ]
}
```

Cover every cue once in original order. Categories: important, context, uncertain, duplicate, filler, false_start, off_topic, low_value. Only KEEP/EXCLUDE are valid actions. Cite a retained cue in `duplicate_of` for duplicates; use null otherwise. Confidence must be finite in 0..1. Do not emit timestamps, approvals or rewritten speech. Numbers and explicit protected terms cannot be automatically excluded. Conservative duplicates need exact text evidence. All strategies retain important/context/uncertain categories. Excluding everything is rejected.

## Review and recovery

The job stores original decisions, editable proposals, applied cut decisions, chronological timeline, remapped SRT and report. Review mode leaves semantic exclusions pending; automatic mode applies only policy-permitted cuts. `target_met=false` reports that the maximum target was not achieved without discarding protected content.

Run the same `auto-edit` command with `--resume` to recover local rendering without another successful cached model request. The work directory binds source SHA-256, transcript fingerprint, editing/model/music settings and offline reply digest. Different inputs need a new directory. `model.pending.json` means billing/submission is uncertain; inspect it and provider history rather than submitting again. `.running` prevents concurrent workers.

The CLI `render PLAN --out OUTPUT` verifies source bounds, protects source files/hard links, checks frame count/canvas/fps/A-V timing and completely decodes the output. It does not verify transcript truth or perceptual lip sync. Full metadata is in the render result; Agent jobs also persist `quality.json` and output SHA-256.
