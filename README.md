# VIDEO-Clips

> Local-first AI video editing toolkit · 本地优先的视频剪辑自动化工程（v0.1.0）

[![Python CI](https://github.com/ForceMind/VIDEO-Clips/actions/workflows/ci.yml/badge.svg)](https://github.com/ForceMind/VIDEO-Clips/actions/workflows/ci.yml)

VIDEO-Clips connects a **vendor-neutral, executable FFmpeg timeline** with optional, **separately installed** Jianying Headless / Agent Skills and the StepAudio 2.5 ASR API. It can validate structured edit plans, cut/reorder clips, insert gaps, keep/adjust original audio, mix additional audio tracks, burn timed captions, and export MP4 on Windows/macOS/Linux.

**VIDEO-Clips is not Jianying, not affiliated with CapCut/ByteDance/StepFun, and does not ship Jianying binary libraries or third-party source covered by non-commercial/no-redistribution licenses.** The optional adapters require separately obtained authorized local installations. See [source and license boundaries](docs/SOURCES-AND-LICENSES.md).

## Current functionality

| Subsystem | Status | Notes |
|---|---|---|
| Local timeline + FFmpeg renderer | Implemented + smoke tested | cut/trim, reorder, speed, original audio, separate audio mix, gaps, letterboxing, SRT burn, MP4 |
| Subtitle SRT import/export | Implemented | SRT requires timings; text-only transcription cannot magically infer word times |
| StepAudio 2.5 ASR | SSE text client + offline file-result subtitle importer | paid API key required for SSE; no live paid call tested; file result must contain actual utterance timestamps |
| Openverse audio search | Implemented, mocked tests | metadata + license filters, no automatic asset downloading |
| Jianying Headless integration | Adapter + plan converter | externally installed private/local core; native OS/version/hash requirements remain |
| yichen-asr Skill router | External adapter | local authorized Skill checkout required; routes text/timestamp needs |
| Native Jianying 11.6 headless MP4 export | Not supported | upstream itself requires UI export for 11.6 |
| AI semantic clip selection / accurate word-level alignment | Not yet implemented | transcription is separate from editorial decision-making |

## Quick start

Requires **Python 3.10+**, `ffmpeg` and `ffprobe` on `PATH`.

```bash
python -m venv .venv
# Activate it, then:
python -m pip install -e .
video-clips doctor
```

Put a short test video at `examples/recording.mp4` (or replace `source` in the sample plan with an absolute path):

```bash
video-clips validate examples/example.plan.json
video-clips render examples/example.plan.json --out ./preview.mp4
video-clips captions examples/example.plan.json --out ./preview.srt
```

`render` will not overwrite an existing MP4 unless `--overwrite` is explicitly supplied. Inputs are always read-only; caption import saves a **new** plan rather than changing the original.

### Example edit plan

```json
{
  "schema": "video-clips/v1",
  "name": "Game trailer",
  "canvas": { "width": 720, "height": 1280, "fps": 30 },
  "video": [
    { "source": "/path/to/gameplay.mp4", "start_ms": 0, "source_start_ms": 2000, "duration_ms": 2500, "speed": 1.0, "volume": 0.6 }
  ],
  "audio": [
    { "source": "/path/to/music.mp3", "start_ms": 0, "source_start_ms": 0, "duration_ms": 2500, "volume": 0.2 }
  ],
  "captions": [
    { "text": "PLAY NOW", "start_ms": 100, "duration_ms": 1900 }
  ]
}
```

`duration_ms` is **output timeline duration**; `source_start_ms` is the source in-point; source duration consumed is `duration_ms × speed`. Primary video clips cannot overlap. Separate audio clips may overlap. Relative media paths resolve relative to the **plan**, not the current working directory. No remote media URLs are accepted.

## The three integrations discussed in the original post

1. **Jianying Headless (replacement source):** [`wtcbill/jianying-headless`](https://github.com/wtcbill/jianying-headless), specifically the archived upstream commit `27c2627bbd0fccc8484000f32e9d66a820f4b698`. Its standalone source remains third-party code under a restrictive license; never copy it into this public repository. The adapter uses `JIANYING_HEADLESS_ROOT`.
2. **AI editing Skills:** [`mcncarl/yichen-skills`](https://github.com/mcncarl/yichen-skills) still carries `yichen-asr`, but its current `main` no longer contains `yichen-jianying-edit`; **the preserved editing Skill is inside the `wtcbill` Jianying Headless snapshot** at `skills/yichen-jianying-edit/`. Use an authorized local Skill checkout via `YICHEN_SKILLS_ROOT` for routing; the native entrypoint comes from the external Jianying checkout.
3. **StepAudio 2.5 ASR:** [`platform.stepfun.com`](https://platform.stepfun.com/), a **hosted API, not a GitHub repository**. Use an explicitly supplied `STEPFUN_API_KEY` and `video-clips step-asr`. Audio is transmitted to the provider when that command is used; fees may be incurred.

The same post also mentions **Openverse**; VIDEO-Clips exposes its audio search API and preserves attribution information.

### StepAudio 2.5 ASR (paid, explicitly invoked)

```bash
export STEPFUN_API_KEY='YOUR_NORMAL_API_KEY'  # environment only; never commit keys
video-clips step-asr /path/to/voice.mp4 --out ./transcript.json --language zh
```

The client sends a **single** SSE request to `/v1/audio/asr/sse`, stores a content-bound result, and blocks automatic resubmission if completion is uncertain. The endpoint returns authoritative transcript **text**, but this flow does not provide precise word-level timing; do not use it as a substitute for a timestamp/forced-alignment engine. No payment or API invocation happens during `doctor`, `validate`, or local `render`.

### Search Openverse for usable sounds

```bash
video-clips openverse 'game win sound' --commercial --limit 10
```

This is a metadata search. Check each asset's original page and attribution obligations before downloading/using it. The `--commercial` filter omits known non-commercial license categories, but does not confer a commercial license.

### Optional original Jianying workflow (Apple Silicon Mac)

Install the separately authorized source locally, outside this repository. Then:

```bash
export JIANYING_HEADLESS_ROOT='/absolute/path/to/jianying-headless'
video-clips jianying doctor
video-clips jianying-plan examples/example.plan.json --out ./jianying.plan.json
video-clips jianying build --plan ./jianying.plan.json --out ./work/native-build
video-clips jianying verify-build --build ./work/native-build
```

The converter covers a **simple linear subset** of the original `jy14-headless-plan/v1`; it cannot guarantee acceptance by every Jianying build. The upstream exact version/ABI/hash checks are intentionally preserved. **Do not** edit the original scripts or relax their checks to force an incompatible version to run.

To check a separately installed `yichen-asr` router without submitting media:

```bash
export YICHEN_SKILLS_ROOT='/absolute/path/to/yichen-skills'
video-clips yichen-route-asr --provider auto --timestamps --srt
```

### Convert StepFun timestamp results into editable subtitles (offline)

StepAudio 2.5 **SSE** returns text without accurate timestamps. For timed
subtitles, obtain an **asynchronous file ASR** result using StepFun's
`POST /v1/audio/asr/file/submit` (`show_utterances=true`) and the corresponding
`POST /v1/audio/asr/file/query`. This step uses an independently authorized
external API client; VIDEO-Clips does **not** automatically upload media or
submit a paid request for this command.

```bash
video-clips step-file-srt ./completed-step-query.json --out ./captions.srt
video-clips import-srt examples/example.plan.json --srt ./captions.srt --out ./captioned.plan.json
video-clips render ./captioned.plan.json --out ./captioned.mp4
# Optional: video-clips jianying-plan ./captioned.plan.json --out ./captioned.jianying.json
```

If the response has two audio channels, select one with `--channel 0` or
`--channel 1`; mixing overlapping speakers into a single caption track is not
silently attempted. Missing times, failed/running jobs and overlapping
utterances are rejected, rather than inventing caption positions.

See [original sources and licensing](docs/SOURCES-AND-LICENSES.md) for the
restored Jianying link and for the difference between GitHub repositories,
Agent Skill directories and the hosted StepFun API.

## Tests

```bash
python -m unittest discover -s tests -v
```

The unit suite includes FFmpeg integration rendering against synthetic locally generated media, Step SSE parsing/error/duplicate-submission scenarios, plan validation, SRT and Openverse license filtering. It does **not** run a paid Step request or claim Jianying native GUI/export acceptance.

## Developer references

- [Integration architecture and acceptance boundaries](docs/INTEGRATION.md)
- [Source versions and redistribution limitations](docs/SOURCES-AND-LICENSES.md)
- [Delivery roadmap](docs/ROADMAP.md)

Only this repository's independently authored code is licensed under the [MIT License](LICENSE). Third-party sources and media retain their own terms.
