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
            with patch("video_clips.step_asr._bytes_from_media", return_value=(b"normalized", ".mp3")), patch("video_clips.step_asr.urllib.request.urlopen", return_value=response) as open_:
                result = transcribe(path, output, api_key="test-key")
                self.assertEqual(result["text"], "test")
                self.assertEqual(open_.call_count, 1)
                self.assertEqual(open_.call_args[0][0].full_url, ENDPOINT)
                transcribe(path, output, api_key="test-key")
                self.assertEqual(open_.call_count, 1)
                with self.assertRaisesRegex(ASRError, "language"):
                    transcribe(path, output, api_key="test-key", language="en")
                self.assertEqual(open_.call_count, 1)
            self.assertFalse((root / "done.json.pending.json").exists())

    def test_incomplete_submission_locks_retries(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.mp3"
            path.write_bytes(b"fake-audio")
            out = Path(temp) / "result.json"
            response = FakeResponse([b'data: {"type":"transcript.text.delta","delta":"incomplete"}\n'])
            with patch("video_clips.step_asr._bytes_from_media", return_value=(b"normalized", ".mp3")), patch("video_clips.step_asr.urllib.request.urlopen", return_value=response) as open_:
                with self.assertRaises(ASRError):
                    transcribe(path, out, api_key="test-key")
                self.assertTrue((Path(temp) / "result.json.pending.json").exists())
                with self.assertRaisesRegex(ASRError, "previous request"):
                    transcribe(path, out, api_key="test-key")
                self.assertEqual(open_.call_count, 1)


class NormalizationTests(unittest.TestCase):
    def test_audio_duration_limit_fails_before_normalization(self):
        from video_clips.step_asr import _bytes_from_media
        with patch('video_clips.step_asr.audio_duration_ms', return_value=1800001), patch('video_clips.step_asr.subprocess.run') as process:
            with self.assertRaisesRegex(ASRError, '30 minutes'):
                _bytes_from_media(Path('long.mp3'))
            process.assert_not_called()

    @unittest.skipUnless(__import__('shutil').which('ffmpeg') and __import__('shutil').which('ffprobe'), 'FFmpeg unavailable')
    def test_real_stereo_input_is_normalized_to_declared_rate_and_channels(self):
        import subprocess
        from video_clips.step_asr import _bytes_from_media
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); source=root/'stereo.wav'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:sample_rate=44100:duration=1',
                '-ac','2',str(source)],check=True,capture_output=True)
            audio,suffix=_bytes_from_media(source)
            self.assertEqual(suffix,'.mp3')
            normalized=root/'normalized.mp3';normalized.write_bytes(audio)
            probe=subprocess.run(['ffprobe','-v','error','-show_entries','stream=sample_rate,channels','-of','json',
                str(normalized)],check=True,capture_output=True,text=True)
            stream=json.loads(probe.stdout)['streams'][0]
            self.assertEqual((stream['sample_rate'],stream['channels']),('16000',1))
