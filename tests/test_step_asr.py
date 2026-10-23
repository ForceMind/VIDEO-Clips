import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from video_clips.step_asr import parse_sse, build_payload, ASRError, transcribe, ENDPOINT


class FakeResponse:
    def __init__(self, lines):
        self.lines = lines
    def __iter__(self):
        return iter(self.lines)
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class ASRTests(unittest.TestCase):
    def test_sse_done_authoritative(self):
        result = parse_sse([
            b'data: {"type":"transcript.text.delta","delta":"wrong"}\n', b'\n',
            'data: {"type":"transcript.text.done","text":"correct","usage":{"input_tokens":12}}\n',
            '\n', 'data: [DONE]\n'])
        self.assertEqual(result["text"], "correct")
        self.assertEqual(result["usage"]["input_tokens"], 12)

    def test_missing_done_rejected(self):
        with self.assertRaises(ASRError):
            parse_sse([b'data: {"type":"transcript.text.delta","delta":"partial"}\n'])

    def test_error_not_silenced(self):
        with self.assertRaisesRegex(ASRError, "blocked"):
            parse_sse([b'data: {"type":"error","message":"blocked"}\n'])

    def test_api_body(self):
        result = build_payload(b"audio", ".mp3", language="zh")
        self.assertEqual(base64.b64decode(result["audio"]["data"]), b"audio")
        self.assertEqual(result["audio"]["input"]["transcription"]["model"], "stepaudio-2.5-asr")

    def test_explicit_submit_once_and_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "sample.mp3"
            path.write_bytes(b"fake-audio")
            output = root / "done.json"
            response = FakeResponse([b'data: {"type":"transcript.text.done","text":"test","usage":{}}\n', b'\n'])
            with patch("video_clips.step_asr.urllib.request.urlopen", return_value=response) as open_:
                result = transcribe(path, output, api_key="test-key")
                self.assertEqual(result["text"], "test")
                self.assertEqual(open_.call_count, 1)
                self.assertEqual(open_.call_args[0][0].full_url, ENDPOINT)
                transcribe(path, output, api_key="test-key")
                self.assertEqual(open_.call_count, 1)
            self.assertFalse((root / "done.json.pending.json").exists())

    def test_incomplete_submission_locks_retries(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.mp3"
            path.write_bytes(b"fake-audio")
            out = Path(temp) / "result.json"
            response = FakeResponse([b'data: {"type":"transcript.text.delta","delta":"incomplete"}\n'])
            with patch("video_clips.step_asr.urllib.request.urlopen", return_value=response) as open_:
                with self.assertRaises(ASRError):
                    transcribe(path, out, api_key="test-key")
                self.assertTrue((Path(temp) / "result.json.pending.json").exists())
                with self.assertRaisesRegex(ASRError, "previous request"):
                    transcribe(path, out, api_key="test-key")
                self.assertEqual(open_.call_count, 1)
