# Windows FFmpeg export

Windows uses an isolated FFmpeg renderer. It produces a verified MP4, not a
Jianying-native editable draft, and never imports the macOS codec, registration,
account or resource-cache modules.

## Requirements

- Python 3.9 or newer.
- FFmpeg and FFprobe containing H.264, AAC, overlay and drawtext support.
- An explicit local TTF, OTF or TTC file when the plan contains text.

Executables resolve from the command options first, the JIANYING_FFMPEG and
JIANYING_FFPROBE environment variables second, and PATH last.

## Build, verify and export

~~~powershell
python skills\yichen-jianying-edit\scripts\headless_draft.py build --plan D:\input\plan.json --out D:\jianying-headless\work\windows-build
python skills\yichen-jianying-edit\scripts\headless_draft.py verify-build --build D:\jianying-headless\work\windows-build
python skills\yichen-jianying-edit\scripts\headless_draft.py export --backend windows-ffmpeg --build D:\jianying-headless\work\windows-build --out D:\jianying-headless\work\windows-export --font C:\Windows\Fonts\msyh.ttc
~~~

On Windows the Windows backend is the default. The build stores a deterministic
render timeline and all media below the render directory; build.json binds the
plan, timeline and every resource by SHA-256. Absolute timeline media paths,
parent traversal, symlinks, unknown dependencies and post-build changes are
rejected. The supplied font is separately snapshotted into the export job and
recorded by name, size and SHA-256.

The renderer supports ordered video, overlay video, target-time gaps, cuts,
speed, original audio, separate audio tracks, volume, still inputs and basic
text. Audio is placed on the absolute target timeline, so silent clips do not
collapse later audio. Sequential and overlapping text tracks form one connected
filter chain. Native effects, filters, transitions, keyframes and editable
Windows Jianying drafts are explicitly unsupported.

Successful output retains render.mp4, result.json, the filter graph, FFprobe
evidence and FFmpeg/full-decode logs. The result asserts duration, dimensions,
frame rate, frame count, H.264/yuv420p output, complete decoding and an unchanged
source build. An exact frame-aligned timeline requires the exact frame count;
only a genuinely fractional duration accepts its adjacent integer counts.
The audio mix does not normalize against its silent timing bed, so an explicit
volume such as 0.5 retains its requested gain.

## Verification

~~~powershell
python tools\check_package.py
python -m unittest engine.test_windows_ffmpeg -v
python tools\windows_ci_evidence.py
~~~

The GitHub workflow uses a normal pull_request event with read-only permissions.
It downloads one reviewed FFmpeg archive by release asset ID, rejects any other
bytes by exact SHA-256, and fails unless `ffmpeg` and `ffprobe` resolve to that
archive and report the pinned version. Evidence uses the repository's reviewed,
redistributable public-media fixture; private drafts, account data, system fonts
and source paths are not uploaded. The public IG case also checks the rendered
audio mean level against its requested 0.5 gain and retains a path-free
`audio-gain.json` report.

### CI FFmpeg source

| Field | Pinned value |
| --- | --- |
| Build | gyan.dev FFmpeg 8.1.2 essentials, static x64, GPLv3 (`8.1.2-essentials_build-www.gyan.dev`) |
| Release | [GyanD/codexffmpeg 8.1.2](https://github.com/GyanD/codexffmpeg/releases/tag/8.1.2), published 2026-06-27 |
| Asset | `ffmpeg-8.1.2-essentials_build.zip`, asset ID 459500679, 109,728,040 bytes |
| SHA-256 | `db580001caa24ac104c8cb856cd113a87b0a443f7bdf47d8c12b1d740584a2ec` |

Reviewed on 2026-10-15. The downloaded bytes match both the digest GitHub
records for the asset and the checksum published by gyan.dev. The archive has
one top-level folder with `ffmpeg.exe`, `ffprobe.exe`, `ffplay.exe`, license,
readme, presets and HTML documentation; it has no DLLs, scripts, links or parent
paths. Both tools are x64 executables whose embedded configuration enables
libx264, libfreetype, libharfbuzz and libfribidi; the AAC encoder is built in.

The earlier BtbN autobuild pins (assets 574819415 and 583988006, the latter
FFmpeg n8.1.3) were pruned upstream and now return HTTP 404. gyan.dev has kept
its versioned GitHub releases since 2020, so CI pins one of those instead. If
this asset disappears or changes, the job fails closed. Restore identical bytes
or review a replacement and update this table and the workflow together; never
remove or loosen the digest check.
