"""Verify the actual distribution contains importable modules and all UI assets."""
import argparse
from pathlib import Path
import zipfile

parser=argparse.ArgumentParser();parser.add_argument('directory');args=parser.parse_args()
target=Path(args.directory)
wheels=[target] if target.is_file() else sorted(target.glob('*.whl'),key=lambda p:p.stat().st_mtime)[-1:]
if not wheels:raise SystemExit('No wheel was built')
for wheel in wheels:
    with zipfile.ZipFile(wheel) as archive:
        names=set(archive.namelist())
        required={'video_clips/web/'+name for name in ('index.html','app.js','style.css')}
        required.update('video_clips/'+name for name in ('cli.py','agent.py','llm.py','pipeline.py','local_ui.py','batch.py','quality.py'))
        missing=required-names
        if missing:raise SystemExit('Wheel missing required files: '+str(sorted(missing)))
    print(str(wheel)+': required code and all web assets verified')
