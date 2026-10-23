import io
import json
import unittest
from unittest.mock import patch
from video_clips.openverse import search_audio


class FakeContext:
    def __init__(self, content):
        self.buffer = io.BytesIO(json.dumps(content).encode())
    def __enter__(self):
        return self.buffer
    def __exit__(self, *args):
        pass


class OpenverseTests(unittest.TestCase):
    def test_commercial_license_filter(self):
        payload = {"results": [
            {"title": "commercial", "license": "by", "url": "https://example.org/s.mp3"},
            {"title": "noncommercial", "license": "by-nc", "url": "https://example.org/s2.mp3"},
            {"title": "public domain", "license": "cc0", "url": "https://example.org/s3.mp3"},
        ]}
        with patch("video_clips.openverse.urlopen", return_value=FakeContext(payload)):
            result = search_audio("pop", commercial=True)
            self.assertEqual([r["title"] for r in result], ["commercial", "public domain"])
    def test_invalid_query_no_request(self):
        with self.assertRaises(ValueError):
            search_audio(" ")
