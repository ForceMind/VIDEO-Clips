#!/usr/bin/env python3
"""Cross-platform local bootstrap; no hosted deployment or bundled FFmpeg download."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import venv


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--workspace',default='.')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--check',action='store_true',help='check prerequisites without creating an environment')
    parser.add_argument('--refresh',action='store_true',help='reinstall the current repository into its local venv')
    args=parser.parse_args(argv)
    if sys.version_info<(3,10):raise RuntimeError('Python 3.10 or later is required')
    missing=[name for name in ('ffmpeg','ffprobe') if not shutil.which(name)]
    if missing:
        raise RuntimeError('Missing '+', '.join(missing)+'. Install FFmpeg first: Windows winget install Gyan.FFmpeg; macOS brew install ffmpeg; Debian/Ubuntu sudo apt-get install ffmpeg.')
    workspace=Path(args.workspace).expanduser().resolve(strict=True)
    if not workspace.is_dir():raise ValueError('workspace must be an existing directory')
    if not 0<=args.port<=65535:raise ValueError('port must be 0..65535')
    if args.check:
        print('Python, FFmpeg, FFprobe and workspace are ready.');return 0
    repo=Path(__file__).resolve().parents[1];environment=repo/'.venv'
    executable=environment/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
    if not executable.is_file():venv.EnvBuilder(with_pip=True).create(environment)
    digest=hashlib.sha256()
    for source in [repo/'pyproject.toml',*sorted((repo/'src').rglob('*'))]:
        if source.is_file() and '__pycache__' not in source.parts and source.suffix in {'.py','.toml','.html','.css','.js'}:
            digest.update(source.relative_to(repo).as_posix().encode());digest.update(source.read_bytes())
    marker=environment/'video-clips-source.sha256'
    identity=digest.hexdigest()
    if args.refresh or not marker.is_file() or marker.read_text().strip()!=identity:
        subprocess.run([str(executable),'-m','pip','install','--no-deps',str(repo)],check=True)
        marker.write_text(identity+'\n')
    return subprocess.call([str(executable),'-m','video_clips','ui','--workspace',str(workspace),'--port',str(args.port)])


if __name__=='__main__':
    try:raise SystemExit(main())
    except KeyboardInterrupt:raise SystemExit(130)
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:
        print('VIDEO-Clips startup: '+str(exc),file=sys.stderr);raise SystemExit(2)
