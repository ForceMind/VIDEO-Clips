# Source preservation and upstream backups

The baseline of independently authored VIDEO-Clips code has been frozen in [`backup/source-snapshot-20261023`](https://github.com/ForceMind/VIDEO-Clips/tree/backup/source-snapshot-20261023) (original baseline `c2d902ee6b4e7e9ab2e0346419a90a565d5ea229`). Continued development takes place on `main`.

The backup branch includes:

- The full Git-tracked VIDEO-Clips source snapshot, including CLI, renderer, adapters, tests and CI.
- `backup/upstream-sources.json`: pinned repository URLs, commits and root Git trees.
- `backup/upstream-file-index.json`: file paths, Git object hashes and sizes for **343** files in the two GitHub source repositories.
- `tools/create_private_source_backup.py`: a script that a user may run **locally** to clone the two upstream repositories, verify pinned commits, and make full-history Git bundles.

Pinned external repositories:

- [wtcbill/jianying-headless](https://github.com/wtcbill/jianying-headless) at `27c2627bbd0fccc8484000f32e9d66a820f4b698`. Includes `skills/yichen-jianying-edit/`.
- [mcncarl/yichen-skills](https://github.com/mcncarl/yichen-skills) at `6e0c0ae43b5fd168040b8eb5193392e47b6f6301`. Includes `yichen-asr`. Its newer commit removed the old `yichen-jianying-edit` directory; that component remains in the preserved Jianying snapshot.

**Verified 2026-10-23:** The branch at `1afe29dd23fac61c27d8a98a4aa17e9ec8d1cdb5` actually contains 106 Jianying and 235 Yichen upstream files under `backup/upstream/`, in addition to the metadata/helper. Earlier documentation incorrectly described it as metadata-only. Every copied blob matches its pinned upstream Git object. Two Jianying MP4 demo files are absent. Their pinned objects were retrieved and both Git SHA-1 and SHA-256 verified in cloud scratch; see [integrity record](upstream-integrity-20261023.json). The preserved branch has not been changed.

All branches here are public. The actual upstream licenses restrict packaged public redistribution and commercial use. Further third-party sources/media are not added to product branches; native integration uses separately obtained authorized local checkouts. Existing upstream notices/licenses are retained.

To build an actual self-contained backup for *personal local use*, check out the backup branch in your own authorized environment and run:

```bash
python tools/create_private_source_backup.py --destination /path/to/new/private/offline-backup
```

The helper creates both `*.git` mirror clones and verifiable `*.bundle` histories and writes a SHA-256 manifest. It never automatically uploads the retrieved third-party source to VIDEO-Clips. Follow the original license terms, especially the non-commercial and redistribution restrictions.

StepAudio 2.5 ASR is a hosted API service, not an additional source Git repository. Openverse is an external media search service; individual media assets have independent licenses.
