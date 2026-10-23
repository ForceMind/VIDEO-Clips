# Auditable speech-timed rough cuts

`video-clips rough-cut` is an offline, non-destructive compiler from **already time-aligned** speech transcripts to the vendor-neutral `video-clips/v1` edit plan. It does not download media, call ASR APIs or consume credits. It works on Windows, macOS and Linux with locally installed FFprobe and FFmpeg; an authorized separately installed Jianying adapter can subsequently convert the plan.

## Inputs and outputs

- One local video with a video stream (`source`), no remote URLs. FFprobe supplies image size, duration and an approximate integer FPS for the plan; only integral FPS 1–60 is supported by this version.
- EITHER an existing `--srt` with proper chronological nonoverlapping cue times, OR `--step-file` containing a **completed** StepFun `/v1/audio/asr/file/query` response with `show_utterances=true` timestamps. Multichannel responses require `--channel INDEX`. The one-shot StepAudio SSE *text* response is **not** a valid timing source.
- Optional `--decisions FILE` with explicit, manually reviewed or agent-proposed 1-based cue exclusions and written reasons. Numbers/dates/money/percentages are protected by default, override only with `--allow-numeric-exclusion` after checking.
- A new `*.plan.json` and sibling `*.review.json` by default (`--report` can set another path). Existing outputs are not overwritten. The original video and subtitles are read-only.

## Algorithm and limitations

1. Reject empty/out-of-order/overlapping/too-long transcripts and inconsistent video duration.
2. For each retained utterance, expand source coverage by `--padding-before-ms` (default 120) and `--padding-after-ms` (default 160), within original video bounds.
3. Quantize coverage to output frame boundaries. Merge neighboring retained spans only if the gap after padding is ≤ `--merge-gap-ms` (default 650). **Never merge across a specifically excluded utterance**, and don't allow padding to include it.
4. Rebase start times of each retained subtitle onto the concatenated destination timeline. Copy full source media path, speed 1 and original audio into each primary video clip. Output a JSON plan accepted by `video-clips validate`, `render`, and the bounded Jianying plan converter.
5. Write the exact kept time ranges, omitted ranges, excluded cue text/reasons and safety warnings to the review report. These `removed_ranges` mean *no transcript coverage*, **not measured silence**. A music interlude, important visual shot, sound effect or ASR missed utterance might be removed. Review them before accepting.

This initial deterministic compiler **cannot** identify repeated claims, select highlights or remove semantic filler unless the caller supplies explicit exclusion decisions. No forced word-level alignment, background music ducking, crossfades or audio cleanups are implied. MP4 cut points are approximate on codecs with long GOPs, so use the rendered preview as the authority.

## Example

```bash
video-clips step-file-srt step-response.json --out original.srt
video-clips rough-cut source.mp4 --step-file step-response.json \
  --padding-before-ms 100 --padding-after-ms 200 --merge-gap-ms 600 \
  --out output/rough.plan.json
video-clips render output/rough.plan.json --out output/rough.mp4
video-clips jianying-plan output/rough.plan.json --out output/rough.jianying.json
```

Exclude an identified repeated cue only after reviewing the transcript:

```json
{"schema":"video-clips/cut-decisions/v1","exclude":[{"cue":4,"reason":"Repeated previous sentence"}]}
```

Then use `--decisions reviewed.json`. A separate audit report records the reason and position for each omission. ASR output still requires human or automated quality control before posting.

## Verification

Run `python -m unittest discover -s tests -v`. The suite includes real, synthetic FFmpeg video generation, time-aligned rough-cut compilation, subtitle remapping, real MP4 render, validation of reports/duplicate decisions, overlap checks and numerical protection. These are local tests, not evidence of Mac Jianying native support or accurate third-party ASR transcripts.
