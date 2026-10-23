import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from video_clips.llm import ModelConfig, complete


class CompatibleServer:
    def __enter__(self):
        owner = self
        self.calls = []
        self.status = 200
        self.finish = 'stop'
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                owner.calls.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(owner.status)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'choices':[{'finish_reason':owner.finish,
                    'message':{'content':json.dumps(owner.reply)}}], 'usage':{'total_tokens':100}}).encode())
            def log_message(self, *args): pass
        self.reply = {'ok': True}
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.config = ModelConfig(f'http://127.0.0.1:{self.server.server_port}/v1/chat/completions', 'test-local')
        return self
    def __exit__(self, *args):
        self.server.shutdown(); self.server.server_close(); self.thread.join()


class ModelTests(unittest.TestCase):
    def test_explicit_opt_in_then_cache_prevents_second_request_and_keys_not_saved(self):
        with CompatibleServer() as server, tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaisesRegex(RuntimeError, 'disabled'):
                complete({'task':'edit'}, server.config, root)
            self.assertEqual(server.calls, [])
            with patch.dict(os.environ, {'VIDEO_CLIPS_MODEL_KEY':'test-secret-value'}):
                first = complete({'task':'edit'}, server.config, root, allow_paid=True)
            self.assertEqual(first['response'], {'ok':True})
            self.assertEqual(complete({'task':'edit'}, server.config, root), first)
            self.assertEqual(len(server.calls), 1)
            self.assertNotIn('test-secret-value', (root/'model-response.json').read_text())
            self.assertFalse((root/'model.pending.json').exists())
            with self.assertRaisesRegex(RuntimeError, 'different request'):
                complete({'task':'changed'}, server.config, root, allow_paid=True)

    def test_http_failure_and_truncation_keep_pending_lock(self):
        for status, finish in [(429, 'stop'), (200, 'length')]:
            with self.subTest(status=status), CompatibleServer() as server, tempfile.TemporaryDirectory() as folder:
                server.status, server.finish = status, finish
                with self.assertRaises(RuntimeError): complete({}, server.config, Path(folder), allow_paid=True)
                with self.assertRaisesRegex(RuntimeError, 'uncertain billing'):
                    complete({}, server.config, Path(folder), allow_paid=True)
                self.assertEqual(len(server.calls), 1)
                self.assertFalse((Path(folder)/'model-response.json').exists())

    def test_endpoint_restrictions_and_limits(self):
        for endpoint in ['http://example.org/api', 'https://name:secret@example.org/api',
                         'https://example.org/api?key=secret', 'ftp://localhost/a']:
            with self.assertRaises(ValueError): ModelConfig(endpoint, 'model').validate()
        with self.assertRaises(ValueError): ModelConfig('https://example.org/api', 'model', max_tokens=True).validate()
