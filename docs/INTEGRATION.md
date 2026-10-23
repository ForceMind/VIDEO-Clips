# VIDEO-Clips integration architecture

## Design

```text
Local sources / user-provided captions
          |
          v
  video-clips/v1 JSON edit plan <-- editorial agent (future)
          |             |                    |
          v             v                    v
      Validator     subtitle SRT       StepAudio 2.5 ASR (text)
          |
          +---------------> Native FFmpeg MP4 renderer (cross-platform)
          |
          +---------------> Jianying plan converter (bounded subset)
                                    |
                                    v
                      separately installed Jianying Headless
                                    |
                             editable native draft

Separately installed yichen-asr Skill router: choose Step text or timestamp-capable
provider, but do not silently change providers after a paid submission.
Openverse search: remote discovery of candidate sound effects with per-item license.
```

## Integration contracts

- `video-clips/v1` is our public source-of-truth. All times are integer **milliseconds**; native Jianying conversion uses integer microseconds. Input media is immutable. The native plan converter guarantees only syntactic field mapping for the documented simple subset, not current-product compatibility.
- `jinaying` external path is **not vendored**; `JIANYING_HEADLESS_ROOT` must refer to a separately installed authorized checkout. Upstream byte-for-byte source integrity checks remain in force. A mismatched copy fails closed.
- `yichen-asr` optional router is **not included**. It can choose a timestamp-capable provider when user needs SRT; its selection output does not replace calling the actual provider. `STEPFUN_API_KEY` is evaluated only for the explicit `step-asr` command.
- Step SSE ASR is text-only in VIDEO-Clips v0.1. Need word/utterance timestamps for quality subtitles and precise semantic deletion; do not invent timestamps from character counts. Pending/ambiguous submissions are never automatically retried or switched providers.
- Openverse is an audio **index**, not a global license. Search results retain attribution, creator, source and license information; download, waveform matching, and automatic insertion are future tasks.
- Native render (`render.py`) works independently of the proprietary editing engine, using subprocess argument lists (not `shell=True`). FFmpeg & FFprobe availability is diagnosed locally.

## Acceptance levels

| Claim | Required evidence | v0.1 |
|---|---|---|
| Native FFmpeg linear editing | synthetic input, MP4 decode/duration, CI tests | implemented locally |
| Step ASR API contract | mocked SSE success/error, content-bound cache | implemented locally |
| Paid Step ASR live service | explicit caller authorization, live API response | **not tested** |
| Native Jianying draft | compatible Mac, native checkout, actual build and cold reopen | **not tested** |
| Original 11.6 native headless export | upstream-compatible snapshot, native output | **upstream does not support yet** |
| Word-level subtitle alignment | timestamp backend + human/QC acceptance | **future** |

## Guardrails

- Never put private API keys, media, user transcripts, protected libraries or licensed upstream source in this public repository.
- Never reuse licensed upstream implementation snippets without required permissions.
- Keep a new work/output directory for each edited movie.
- Do not silently overwrite sources, previously generated projects, or transcripts.
- If Step's SSE stream ends without `transcript.text.done`, consider request state ambiguous and preserve pending metadata. **Do not retry automatically**.
- Do not bypass licensed asset requirements, paid effects, authentication or native program compatibility checks.
