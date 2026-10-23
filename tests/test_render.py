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

    def test_output_cannot_replace_original_or_hardlink(self):
        from video_clips.pipeline import file_sha256
        from video_clips.plan import PlanError
        original = file_sha256(self.source)
        with self.assertRaisesRegex(PlanError, 'source media'):
            render(self._load(), self.source, overwrite=True)
        link = self.root/'hardlink.mp4'
        try:
            link.hardlink_to(self.source)
        except OSError:
            self.skipTest('hard links unavailable')
        with self.assertRaisesRegex(PlanError, 'source media'):
            render(self._load(), link, overwrite=True)
        self.assertEqual(file_sha256(self.source), original)

    def test_source_range_beyond_media_rejected_before_output(self):
        from video_clips.plan import PlanError
        self.data['video'][0]['source_start_ms'] = 1800
        with self.assertRaisesRegex(PlanError, 'exceeds media duration'):
            render(self._load(), self.root/'too-long.mp4')
        self.assertFalse((self.root/'too-long.mp4').exists())

    def test_many_non_frame_aligned_clips_do_not_accumulate_frame_drift(self):
        from video_clips.quality import verify_output
        self.data['video'] = [{'source':'source.mp4','start_ms':i*101,'source_start_ms':0,
                               'duration_ms':101} for i in range(24)]
        plan = self._load()
        result = render(plan,self.root/'many.mp4')
        quality = verify_output(plan,result.path,decode=False)
        self.assertEqual(quality['decoded_frames'], round(2.424*12))
        self.assertAlmostEqual(quality['video_duration_s'],2.424,delta=1/12)

    def test_quality_rejects_mismatched_canvas(self):
        from video_clips.quality import verify_output
        from video_clips.plan import PlanError
        output = render(self._load(), self.root/'quality.mp4').path
        self.data['canvas']['width'] = 640
        with self.assertRaisesRegex(PlanError, 'canvas'):
            verify_output(self._load(),output,decode=False)

    def test_speed_and_aspect_are_verified_on_real_output(self):
        from video_clips.quality import verify_output
        self.data['video'][0].update(speed=2.0,duration_ms=750)
        self.data['canvas'].update(width=240,height=320)
        plan = self._load()
        result=render(plan,self.root/'vertical.mp4')
        quality=verify_output(plan,result.path,decode=False)
        self.assertEqual((quality['width'],quality['height']),(240,320))
        self.assertEqual(quality['decoded_frames'],9)
