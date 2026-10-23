# Executable AI editing workflow

`auto-edit` joins the existing timed-ASR import, editorial review, rough-cut compiler and FFmpeg engine. It uses a separately configured Chat Completions compatible model endpoint, including local compatible servers. There is no bundled model, single required vendor, inferred timestamp or automatic paid ASR fallback.

```bash
# Set VIDEO_CLIPS_MODEL_KEY in your local environment; never place it in a plan.
video-clips auto-edit original.mp4 --srt original.srt \
  --instruction "删除口误与重复，保留完整观点，生成竖屏短视频" \
  --strategy standard --target-ms 180000 --protect-term VIDEO-Clips \
  --model-endpoint https://your-provider.example/v1/chat/completions \
  --model your-model --allow-paid-model --apply-ai-cuts \
  --aspect 9:16 --workdir work/first-edit --render

# Resume the SAME source/transcript/options/model configuration:
# Repeat the same command with --resume. Completed model calls are reused.
```

`--step-file completed.json` may replace `--srt`. It must contain completed, nonoverlapping utterance timestamps. The existing Step SSE endpoint returns text only and cannot supply this alignment. Raw video → paid timestamped ASR submission/query is a remaining integration task, not silently simulated here.

Without `--apply-ai-cuts`, semantic EXCLUDE recommendations stay pending and all utterances remain. The underlying speech-timed rough-cut still trims untranscribed intervals; those intervals can contain meaningful visual/audio content. Review `review.json` and the source before publishing. Models do not receive an approval field; the independent compiler applies the explicitly chosen policy.

## Policy

| Strategy | Eligible exclusion categories | Minimum model confidence |
|---|---|---|
| conservative | exact-text duplicates referencing a retained cue; fillers | 0.98 |
| standard | duplicates, fillers, false starts, irrelevant tangents | 0.90 |
| aggressive | standard plus low-value material | 0.90 |
| highlights | relevant highlights retained; standard plus low-value material excluded | 0.90 |

Every cue must appear once in original order with its exact text, KEEP/EXCLUDE, reason, category, confidence and optional duplicate reference. Missing cues, rewritten speech, stale fingerprints, extra time fields, self-approval, invalid references, nonfinite values and duplicate JSON keys are rejected. Numerals and `--protect-term` matches always survive automatic cuts. Context/important/uncertain categories cannot be automatically excluded. Confidence is a model estimate, not a calibrated guarantee; factual/contextual correctness still requires review. Product names are protected through the model instruction and explicit protected terms, not a claimed universal name recognizer.

Targets are advisory. Protected content is never discarded just to hit a duration. `target_met=false` makes failure to meet the requested maximum visible. The first Agent version preserves chronological order; semantic rearrangement, multiple independent highlight videos and arbitrary B-roll reasoning are not implemented. Aspect conversion currently fits with letterboxing/pillarboxing, without face tracking or a claimed intelligent crop.

## Files and recovery

A job directory contains `job.json`, the transcript-bound `request.json`, `agent-response.json`, `proposals.json`, `decisions.json`, `review.json`, `plan.json`, `captions.srt`, and optionally `output.mp4`. Keep it private: it includes media paths and transcript text. Media remain unchanged. Keys are read only from an environment variable. Source SHA-256, transcript fingerprint, editing settings, endpoint and model are bound to the job. Changed inputs require a new directory.

`--response agent-decisions.json` runs the same policy/compiler/render chain offline using an existing model reply; it cannot be combined with a model request. This is useful for deterministic tests and externally produced responses. Use `editorial-brief` to obtain the source transcript fingerprint and cue text. The full reply format is documented in `request.json` and `src/video_clips/agent.py`.

The model client makes at most one request per cache identity, bounds input/output sizes and token budget, rejects remote plain HTTP and redirects, and requires explicit `--allow-paid-model` even for a local HTTP server. Successful replies and usage are cached. A timeout/HTTP/truncation/parse failure retains `model.pending.json`; no automatic paid retry occurs. Inspect provider billing/history before manually clearing an uncertain pending marker. Rendering can be resumed without another cached model request. A `.running` lock prevents concurrent job execution; after a process crash, confirm the worker stopped before removing the lock. This is a single-job recovery mechanism, not yet a distributed queue.

## Export boundaries

- FFmpeg: the implemented local MP4 rendering path.
- `jianying-plan`: conversion to the supported external engine plan subset.
- `jianying build`: invokes a separately installed, appropriately licensed external checkout.
- Native Jianying draft rendering/export: requires compatible native runtimes/assets and possibly GUI interaction; not validated on this Linux cloud host. MP4 from FFmpeg is never described as a native Jianying export.

No paid ASR/model call or third-party media download is performed by the test suite. Tests run a loopback compatible HTTP server, return fixture model decisions, deliberately interrupt rendering, resume without a second POST, and render actual H.264/AAC MP4 from synthetic media.
