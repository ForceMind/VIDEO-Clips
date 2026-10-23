# Preserved upstream source snapshots

This folder contains **independent Git snapshots of the referenced upstream sources for personal backup and research**, not components of the VIDEO-Clips MIT-licensed distribution. Original license and attribution notices are preserved verbatim within each source tree. Do not merge these archived files into the public VIDEO-Clips product, commercialize, or repackage them without the relevant rights. The VIDEO-Clips MIT license does **not** relicense third-party materials.

## 1. Jianying Headless + bundled yichen-jianying-edit Skill

Original project (currently unavailable): https://github.com/mcncarl/jianying-headless
Available replacement: https://github.com/wtcbill/jianying-headless
Pinned HEAD: `27c2627bbd0fccc8484000f32e9d66a820f4b698`

- `jianying-headless/` preserves **106 of 108 upstream tracked files** with identical Git blob IDs and modes, including **all 104 source/configuration/doc/test files** plus both PNG preview image files.
- Excluded: two binary demonstration MP4 videos larger than the connected GitHub text transfer limit:
  - `docs/media/hypit-original-preview.mp4` — `baa864959cec361d66b2a0dd5fa7bd71bbbac0cb`, 4,421,052 bytes
  - `docs/media/jianying-import-preview.mp4` — `60127bda902f31ac8e2db779ab98d64af442539f`, 4,223,556 bytes
- The missing MP4s are *example output media*, not code, and can be recovered from the pinned upstream commit while that repository is accessible. The native Jianying application, paid visual assets and installed libraries were not published in the upstream repo in the first place.

## 2. Yichen Skills

Source: https://github.com/mcncarl/yichen-skills
Pinned HEAD: `6e0c0ae43b5fd168040b8eb5193392e47b6f6301`

- `yichen-skills/` preserves **all 235 upstream tracked files**, including text sources, license and the single JPEG asset, with identical Git blob IDs and modes.
- The current upstream HEAD removed the separate `yichen-jianying-edit` Skill folder. Its preserved version is under the **Jianying Headless** archive: `jianying-headless/skills/yichen-jianying-edit/`.

## 3. Hosted integrations, not Git source repositories

StepAudio 2.5 ASR: https://platform.stepfun.com/ — third-party hosted speech recognition service.
Openverse: https://openverse.org/ — audio/visual media search service with per-asset licensing.

## What counts as a complete backup?

These GitHub archive directories represent source **file snapshots**. They do not embed the original Git *commit graphs*, and are not a byte-for-byte complete repo mirror because the two named MP4s are missing.

For a fully restorable **private** backup including commit histories and binary demonstrations, run the included offline script from a machine with Git access:

```bash
python tools/create_private_source_backup.py --destination /absolute/private/backup/path
```

It creates pinned Git bundles and SHA-256 checksums, and does not change your personal files or upload third-party sources to any other repository. The archive branch is kept separate from `main`, where product development continues with independently implemented adapters.
