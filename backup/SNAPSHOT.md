# Backup branch — 2026-10-23

This branch is a complete Git snapshot of **VIDEO-Clips' own source** at `c2d902ee6b4e7e9ab2e0346419a90a565d5ea229`. Git branches already preserve all files tracked by that commit, so duplicating the whole application into a second directory would add no protection.

## Pinned external sources

- **Preserved Jianying Headless + editing Skill:** [wtcbill/jianying-headless](https://github.com/wtcbill/jianying-headless) at `27c2627bbd0fccc8484000f32e9d66a820f4b698`; all original engine/bridge and `skills/yichen-jianying-edit` code are there.
- **Yichen ASR routing Skills:** [mcncarl/yichen-skills](https://github.com/mcncarl/yichen-skills) at `6e0c0ae43b5fd168040b8eb5193392e47b6f6301`. Its current main no longer contains `yichen-jianying-edit` — use the preserved snapshot above.
- **StepAudio 2.5 ASR:** [StepFun API platform](https://platform.stepfun.com/), an external hosted service, not a third GitHub codebase.
- **Openverse:** audio discovery API, per-asset licenses apply.

The precise repo commit and tree IDs are in [upstream-sources.json](upstream-sources.json).

## Copyright and visibility

**The target GitHub repository is PUBLIC; so is every branch within it.** The external Jianying/Yichen source licenses limit commercial use and republication/redistribution, so their copyrighted files have deliberately **not** been copied into this public backup branch. This branch is not a full mirror of external code. Renaming the branch to “backup” would not change its public visibility.

To preserve a **private, local** source backup, run:

```bash
python tools/create_private_source_backup.py --destination /YOUR/PRIVATE/LOCAL/BACKUP/DIR
```

This runs `git clone`, checks out the pinned commits, writes Git bundles with history, and records checksums. It does not upload code or require access to the user's Mac through ChatGPT. The directory must be new; the script never overwrites or removes user data. Store backups privately, consistent with the original licenses. To republish in VIDEO-Clips, obtain appropriate explicit rights first.

## Continued work

Product development goes on `main`; this branch remains a pinned snapshot. Additional independently authored changes on `main` must not be mistaken for changes to the upstream backup.
