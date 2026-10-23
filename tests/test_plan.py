import json
import tempfile
import unittest
from pathlib import Path
from video_clips.plan import load_plan, PlanError
from video_clips.jianying import export_plan
from video_clips.subtitles import parse_srt, write_srt


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.context = tempfile.TemporaryDirectory()
        self.addCleanup(self.context.cleanup)
        self.root = Path(self.context.name)
        (self.root / "clip.mp4").write_bytes(b"for parsing only")
        self.data = {"schema": "video-clips/v1", "name": "test",
                     "canvas": {"width": 320, "height": 240, "fps": 25},
                     "video": [{"source": "clip.mp4", "start_ms": 0, "duration_ms": 2000}],
                     "audio": [],
                     "captions": [{"text": "Hello, 世界", "start_ms": 100, "duration_ms": 500}]}

    def plan(self):
        path = self.root / "plan.json"
        path.write_text(json.dumps(self.data))
        return path

    def test_load(self):
        p = load_plan(self.plan())
        self.assertEqual((p.width, p.height, p.fps, p.duration_ms), (320, 240, 25, 2000))
        self.assertEqual(p.videos[0].path, self.root / "clip.mp4")

    def test_reject_overlap(self):
        self.data["video"].append({"source": "clip.mp4", "start_ms": 1000, "duration_ms": 500})
        with self.assertRaisesRegex(PlanError, "overlap"):
            load_plan(self.plan())

    def test_reject_unknown_key(self):
        self.data["canvas"]["encoded"] = True
        with self.assertRaisesRegex(PlanError, "unknown"):
            load_plan(self.plan())

    def test_reject_missing_source(self):
        self.data["video"][0]["source"] = "missing.mov"
        with self.assertRaisesRegex(PlanError, "missing"):
            load_plan(self.plan())

    def test_reject_nonfinite(self):
        self.data["video"][0]["speed"] = float("nan")
        with self.assertRaises(PlanError):
            load_plan(self.plan())

    def test_reject_duplicate_json_key(self):
        (self.root / "plan.json").write_text('{"schema":"video-clips/v1","schema":"video-clips/v1"}')
        with self.assertRaisesRegex(PlanError, "duplicate"):
            load_plan(self.root / "plan.json")

    def test_srt_round_trip(self):
        p = load_plan(self.plan())
        file = write_srt(p.captions, self.root / "captions.srt")
        self.assertEqual(parse_srt(file.read_text()), list(p.captions))

    def test_jianying_mapping(self):
        target = self.root / "native.json"
        export_plan(load_plan(self.plan()), target)
        data = json.loads(target.read_text())
        self.assertEqual(data["schema"], "jy14-headless-plan/v1")
        self.assertEqual(data["tracks"][0]["segments"][0]["duration_us"], 2_000_000)
        self.assertEqual(data["tracks"][1]["segments"][0]["start_us"], 100_000)
        with self.assertRaises(FileExistsError):
            export_plan(load_plan(self.plan()), target)
