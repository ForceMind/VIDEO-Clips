# UI export acceptance

Jianying 11.6.0 has no reviewed headless export ABI, so `export` refuses before
it reads a build. This path exists so a finished file can still be delivered on
that runtime: the **editor's own export dialog** renders, and `ui-export`
checks the result. It renders nothing itself.

This is a **separate evidence tier** from the headless native exporter. Neither
one's acceptance carries over to the other, and nothing here relaxes a gate on
that path — `EXPORT_PROFILES` and its container brands are untouched.

## Commands

```bash
python3 SKILL/scripts/headless_draft.py ui-export plan --build ABSOLUTE_BUILD --out ABSOLUTE_WORK/NEW_JOB
# ... export the registered draft from the editor, following the printed settings ...
python3 SKILL/scripts/headless_draft.py ui-export verify --job ABSOLUTE_WORK/NEW_JOB
```

`plan` verifies the build, proves the **registered draft still equals it**
through the same `verify_live` entry the normal readback uses, freezes the
canvas, frame rate, duration, audio expectation and the exact output path, and
records the draft's file manifest. `verify` re-proves all of that, then checks
the file the dialog wrote.

`--video` points at the file when it is not at the planned path. `--report`
writes the evidence somewhere else as well. Each `verify` run keeps its own
`attempt-NNN/` directory, so a rejected export is never overwritten by a later
one.

## What `verify` actually checks

- The build is unchanged since planning, and the registered draft still equals
  the build (four mirrors, media bytes, home registration, untouched source).
- Canvas, frame rate, duration and audio expectation still match the plan, and
  the editor runtime (version and library hash) has not changed.
- Container is one of the reviewed MP4 brands, one H.264 video stream, at most
  one AAC audio stream, and the audio stream is present when the draft has audio.
- **Exact frame count.** This reuses the headless exporter's own policy, so a
  missing tail frame is refused as a partial deliverable, not tolerated as
  rounding.
- Full decoding with `ffmpeg -xerror`.

Everything a UI run cannot prove on its own is checked here, mechanically. What
it still cannot tell you is whether the picture and sound are right; that needs
viewing the output.

## Two things this path does that the headless one does not

**The container is QuickTime-branded.** The dialog's MP4 preset writes
`major_brand: qt  `. `ui_export.CONTAINER_BRANDS` accepts it alongside
`isom`/`mp41`/`mp42`; the headless exporter's brand set is unchanged and still
refuses `qt  `.

**Exporting modifies the draft.** The headless exporter renders a frozen build
and never touches the live draft. This path has to open the draft, and the
editor writes backups, a new cover and a fresh save while it is open. `verify`
reports exactly what moved under `draft_changes_made_by_exporting`; it does not
fail on it, because opening the draft is how this path renders at all.

The consequence worth planning around: a draft that is the recorded **source of
an edit build** will fail that build's source-unchanged check once you have
UI-exported it. Finish an edit copy's own readback acceptance before exporting
its source through the dialog.

## Operating the dialog

Observed on 11.6.0 (build 13281) on 2026-10-20. No login and no membership are
required; the only membership item, 一键超清, stays off.

| Field | Setting |
| --- | --- |
| 格式 | **MP4** — the dialog defaults to MOV |
| 分辨率 | 原始 (exports at the draft canvas) |
| 帧率 | the draft's own frame rate |
| 导出至 | the job directory from `plan` |
| 音频导出 | off — that is a separate audio file, not the video's audio track |

The output file is named after the draft. After rendering, a finished screen
offers publishing to a third-party platform: **close it, never publish**.

Driving it: open the dialog from **文件 → 导出** rather than the title-bar
button, whose clicks are swallowed when the pointer already rests on it. Setting
the output directory goes through a standard macOS panel; paste the path into
Go to Folder instead of typing it, because its autocomplete truncates long
paths. Prefer exporting several drafts to one remembered directory and sorting
the files afterwards over driving that panel repeatedly.

## Offline regression

```bash
python3 -m unittest discover -s tests -p test_ui_export.py -v
```

Ten cases cover the accepted and refused container brands, that the headless
brand set is not widened, the inherited exact frame-count policy, canvas/rate/
codec/missing-audio strictness, probe immutability, the registered runtime set
being 11.6.0 only and disjoint from `EXPORT_PROFILES`, and the draft-change
report. Offline passes establish nothing about a real export; the acceptance is
in [VERIFICATION.md](VERIFICATION.md).
