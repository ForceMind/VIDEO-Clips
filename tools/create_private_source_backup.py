#!/usr/bin/env python3
"""Create personal offline Git bundles from pinned upstream public sources.

Does not publish or upload third-party source to the public VIDEO-Clips repo.
Requires Git and internet access to the source repositories on the user's machine.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

SOURCES = (
    ("jianying-headless", "https://github.com/wtcbill/jianying-headless.git",
     "27c2627bbd0fccc8484000f32e9d66a820f4b698"),
    ("yichen-skills", "https://github.com/mcncarl/yichen-skills.git",
     "6e0c0ae43b5fd168040b8eb5193392e47b6f6301"),
)


def run(*args: str, cwd: Path | None = None) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=False
    )
    if proc.returncode:
        raise RuntimeError(
            f"git {args[0]} failed (exit {proc.returncode}): {proc.stderr.strip()[:600]}"
        )
    return proc.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True,
                        help="New private local directory; existing paths are rejected")
    args = parser.parse_args(argv)
    dest = args.destination.expanduser().resolve()
    if dest.exists():
        parser.error("destination already exists; choose a new empty path")
    if not dest.parent.is_dir():
        parser.error("destination parent directory does not exist")
    dest.mkdir(mode=0o700)
    manifest = {"format": "video-clips-private-upstream-bundles/v1", "sources": []}
    for name, url, commit in SOURCES:
        checkout = dest / (name + ".git")
        print(f"Fetching {name}...")
        run("clone", "--mirror", url, str(checkout))
        found = run("--git-dir", str(checkout), "rev-parse", "--verify", commit + "^{commit}")
        if found != commit:
            raise RuntimeError(f"upstream snapshot {name} does not contain pinned commit")
        bundle = dest / (name + ".bundle")
        run("--git-dir", str(checkout), "bundle", "create", str(bundle), "--all")
        run("bundle", "verify", str(bundle), cwd=checkout)
        manifest["sources"].append({
            "repository": url, "commit": commit, "bundle": bundle.name,
            "size": bundle.stat().st_size, "sha256": sha256(bundle)
        })
    metadata = dest / "manifest.json"
    with metadata.open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"Backed up {len(manifest['sources'])} repositories to {dest}")
    print("Do not publicly redistribute upstream source without permission.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
