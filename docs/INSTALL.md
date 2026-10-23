# Install and launch

This development version is `0.2.0a1`; it is not a production/native-Jianying release. Obtain this repository, Python 3.10+ and a compatible FFmpeg/FFprobe build on PATH. No model account or service is required for local plans, renders, offline replay or the synthetic demo.

From the checkout, use one command:

```bash
python tools/start.py --workspace /path/to/your/media
```

The launcher checks prerequisites, creates a repository-local `.venv`, installs this checkout's Python package and starts its authenticated loopback UI. It refreshes the environment when authored source changes. Build dependencies may need an internet connection on first install. It does not download FFmpeg executables or create a hosted service.

Check without creating an environment:

```bash
python tools/start.py --workspace /path/to/your/media --check
```

If FFmpeg is missing, install it using your platform's normal package manager:

| Platform | Example prerequisite command |
|---|---|
| Windows | `winget install Gyan.FFmpeg` |
| macOS | `brew install ffmpeg` |
| Debian/Ubuntu | `sudo apt-get install ffmpeg` |

Linux systems also need fonts for Chinese UI/subtitle display; for example `sudo apt-get install fonts-noto-cjk`. Windows/macOS normally provide system CJK fonts. A browser's ability to preview the original codec depends on its own decoder; FFmpeg rendering support is separate.

For manual setup and CLI work:

```bash
python -m venv .venv
# Activate the environment using your platform's standard activation command.
python -m pip install -e .
python -m video_clips doctor
python -m video_clips ui --workspace /path/to/your/media
```

No JavaScript build/runtime dependency is needed to use the application. Node/Playwright are optional development dependencies for browser tests. The Python wheel includes the web assets; `python -m pip wheel --no-deps --wheel-dir dist .` builds it. `python tools/check_wheel.py dist` inspects the actual wheel contents.

Repository Skill: `skills/video-clips/` contains independently authored instructions and UI metadata for compatible Agent hosts. Copy/install that folder through the host's normal Skill mechanism after installing VIDEO-Clips. This project does not install it into the user's global Skills workspace or copy restricted upstream Skills. Local forward validation successfully generated a verified 110-frame MP4 using the Skill and an offline fixture without modifying source media or making a paid request.

For batch processing, see [batch manifest guide](BATCH.md). For the local interface, see [UI guide](LOCAL-UI.md). Native Jianying export still requires the separately authorized external engine and compatible environment.
