# Archived third-party source snapshots (research/backup only)

This backup branch holds source-code snapshots separately from the original VIDEO-Clips product. All original licenses, attribution files and notices remain with their respective sources. **The VIDEO-Clips MIT license does not apply to these archived projects.** Do not merge the upstream directories into the VIDEO-Clips product or distribute them as a newly packaged commercial/public tool without appropriate rights.

## Jianying Headless

Source: https://github.com/wtcbill/jianying-headless
Pinned upstream commit: `27c2627bbd0fccc8484000f32e9d66a820f4b698`

All 104 UTF-8 source, configuration, license, documentation and test files have been copied byte-for-byte (Git blob hashes preserved) under `jianying-headless/`.

The upstream repository also contains **four binary preview assets**, excluded from this source-only snapshot because the connected GitHub text interface cannot transfer raw binary bytes:

- `docs/media/hypit-original-frames.png` (Git blob `226b67bf73142cbcea4244a434ffc27692e11314`)
- `docs/media/hypit-original-preview.mp4` (Git blob `baa864959cec361d66b2a0dd5fa7bd71bbbac0cb`)
- `docs/media/jianying-import-frames.png` (Git blob `c95db67ce87b8fff8b1b58f04fcf9b9a2168a45d`)
- `docs/media/jianying-import-preview.mp4` (Git blob `60127bda902f31ac8e2db779ab98d64af442539f`)

These are visual demonstration files, not the source needed to build or understand the engine. If a bit-for-bit backup including binary demos and the full commit graph is needed, use `tools/create_private_source_backup.py` with Git on your local machine.

## Yichen Skills

Source: https://github.com/mcncarl/yichen-skills
Pinned upstream commit: `6e0c0ae43b5fd168040b8eb5193392e47b6f6301`

To be restored under `yichen-skills/` in the following archive commit. At the pinned commit the separate `yichen-jianying-edit` directory has been removed from that repository; the preserved edit Skill exists inside the Jianying Headless snapshot above.

## Hosted services

StepAudio 2.5 ASR is a hosted API, not a third source-code repository. Openverse is an API for sound-effect search, and each downloaded asset has independent terms.
