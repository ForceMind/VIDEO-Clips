import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from video_clips.plan import load_plan
from video_clips.render import render


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg unavailable")
class RenderTests(unittest.TestCase):
    def setUp(self):
        self.context = tempfile.TemporaryDirectory()
        self.addCleanup(self.context.cleanup)
        self.root = Path(self.context.name)
        self.source = self.root / "source.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=12:duration=2.0",
                        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2.0",
                        "-c:v", "libx264", "-threads", "2", "-c:a", "aac", "-shortest",
                        str(self.source)], check=True, capture_output=True, timeout=30)
        self.data = {"schema": "video-clips/v1", "name": "test", "canvas": {"width": 320,
                     "height": 240, "fps": 12}, "video": [{"source": "source.mp4", "start_ms": 0,
                     "duration_ms": 1000, "source_start_ms": 0}], "audio": [], "captions": []}

    def _load(self):
        path = self.root / "plan.json"
        path.write_text(json.dumps(self.data))
        return load_plan(path)

    def test_render_with_audio(self):
        result = render(self._load(), self.root / "out.mp4")
        self.assertTrue(result.path.stat().st_size > 1000)
        self.assertAlmostEqual(result.duration_s, 1, delta=0.20)
        with self.assertRaises(FileExistsError):
            render(self._load(), self.root / "out.mp4")

    def test_render_with_gap_audio_and_subtitles(self):
        self.data["video"] = [{"source": "source.mp4", "start_ms": 500,
                               "duration_ms": 1000, "source_start_ms": 100, "speed": 1}]
        self.data["captions"] = [{"text": "Hello", "start_ms": 300, "duration_ms": 700}]
        self.data["audio"] = [{"source": "source.mp4", "start_ms": 250,
                               "duration_ms": 1000, "source_start_ms": 0, "volume": 0.2}]
        result = render(self._load(), self.root / "out2.mp4")
        self.assertAlmostEqual(result.duration_s, 1.5, delta=0.2)
