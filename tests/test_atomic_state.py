import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from video_clips.pipeline import atomic_json


class AtomicStateTests(unittest.TestCase):
    def test_transient_windows_reader_lock_preserves_and_replaces_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "job.json"
            path.write_text('{"stage":"previous"}', encoding="utf-8")
            replace = os.replace
            calls = []
            def reader_collision(source, target):
                calls.append(target)
                if len(calls) == 1:
                    self.assertEqual(json.loads(path.read_text())["stage"], "previous")
                    error = PermissionError("reader temporarily prevents deletion")
                    error.winerror = 32
                    raise error
                return replace(source, target)
            with patch('video_clips.pipeline.os.replace', side_effect=reader_collision), patch('video_clips.pipeline.time.sleep'):
                atomic_json(path, {"stage": "completed"})
            self.assertEqual(json.loads(path.read_text())["stage"], "completed")
            self.assertEqual(len(calls), 2)
            self.assertEqual(list(path.parent.glob('.write-*')), [])

    def test_persistent_lock_fails_without_deleting_previous_state(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "job.json"
            path.write_text('{"stage":"previous"}', encoding="utf-8")
            error = PermissionError("persistent destination lock")
            error.winerror = 5
            with patch('video_clips.pipeline.os.replace', side_effect=error), patch('video_clips.pipeline.time.sleep'):
                with self.assertRaises(PermissionError):
                    atomic_json(path, {"stage": "completed"})
            self.assertEqual(json.loads(path.read_text())["stage"], "previous")
            self.assertEqual(list(path.parent.glob('.write-*')), [])
