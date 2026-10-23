# Original sources, provenance and license boundaries

Reviewed 2026-10-23. These are independently operated third-party properties. This document is source attribution and compatibility guidance, **not** a copy of protected source code.

| Component | Source | Evidence / purpose | Policy |
|---|---|---|---|
| Jianying Headless | https://github.com/wtcbill/jianying-headless | replacement Fork from user; commit `27c2627bbd0fccc8484000f32e9d66a820f4b698`, dated 2026-10-21; headless plan, native draft/edit/export | Original `Personal Learning and Non-Commercial Use License` restricts public redistribution and commercial use. Must remain a separately obtained authorized local checkout; no vendoring |
| Original source (unavailable) | https://github.com/mcncarl/jianying-headless | source repository referred to by the original X post; currently 404 | 404 cannot distinguish delete vs private |
| Yichen Skills | https://github.com/mcncarl/yichen-skills | specifically `yichen-jianying-edit`, `yichen-asr`; the latter is routing glue rather than a bundled Step model | Same personal/non-commercial restriction; obtain separately; do not copy into public VIDEO-Clips |
| StepAudio 2.5 ASR | https://platform.stepfun.com/ | external hosted model/API, `stepaudio-2.5-asr` | service terms, pricing, regional privacy/data handling apply; API key remains local; not a GitHub repository |
| Openverse | https://openverse.org/ | public search API to find sound effects | individual media have independent licenses; creator/license metadata retained |
| FFmpeg | https://ffmpeg.org/ | runtime tool for local MP4 video/audio rendering | FFmpeg build licenses depend on compilation; users install it separately |

The `wtcbill` snapshot is **36 commits ahead** of the older Sep 20 tree `344a78f179dc275d76fc39aaaaa27d325254c156` seen in `ss-cmd/capcut-draft` and `Jaylumia/jianying-headless`. The older copies are backups of the **same** original source, not additional engines.

Snapshot **does not** contain official Jianying binaries/assets, account credentials, protected paid effects, or a turnkey ASR backend. Original `yichen-asr` external Step script must be supplied separately. A local authorized clone does not grant republishing rights.

VIDEO-Clips MIT applies **only** to files that this project authors independently. If you secure additional rights from the source owners, any later import needs an explicit license and provenance review.
