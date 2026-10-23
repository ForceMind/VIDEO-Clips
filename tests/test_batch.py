import json
import shutil
import tempfile
import unittest
from pathlib import Path
from video_clips.batch import run_batch
import test_pipeline as fixtures


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg unavailable')
class BatchTests(unittest.TestCase):
    def setUp(self):
        fixtures.PipelineTests.setUp(self)
        self.manifest=self.root/'batch.json'
        self.data={'schema':'video-clips/batch/v1','jobs':[
            {'name':'first','source':'source.mp4','srt':'source.srt','instruction':'Remove hesitations',
             'response':'response.json'},
            {'name':'second','source':'source.mp4','srt':'source.srt','instruction':'Remove hesitations',
             'response':'response.json'}]}
        self.manifest.write_text(json.dumps(self.data))
    def test_real_batch_renders_and_resumes_without_model_calls(self):
        result=run_batch(self.manifest,self.root/'batch-work',apply_cuts=True,render_output=True)
        self.assertEqual(result['state'],'completed',result)
        self.assertEqual(len(result['jobs']),2)
        self.assertTrue((self.root/'batch-work'/'first'/'output.mp4').is_file())
        self.assertEqual(result['jobs'][1]['result']['applied_cuts'],1)
        result=run_batch(self.manifest,self.root/'batch-work',apply_cuts=True,render_output=True,resume=True)
        self.assertEqual(result['state'],'completed',result)
        with self.assertRaises(ValueError):
            run_batch(self.manifest,self.root/'batch-work',apply_cuts=False,render_output=True,resume=True)
    def test_manifest_is_preflighted_and_failed_jobs_do_not_hide_success(self):
        self.data['jobs'][1]['name']='../escape'
        self.manifest.write_text(json.dumps(self.data))
        with self.assertRaises(ValueError):run_batch(self.manifest,self.root/'bad-batch')
        self.assertFalse((self.root/'bad-batch').exists())
        self.data['jobs'][1]['name']='second'
        bad=self.root/'bad-response.json';bad.write_text('{}')
        self.data['jobs'][1]['response']='bad-response.json'
        self.manifest.write_text(json.dumps(self.data))
        result=run_batch(self.manifest,self.root/'partial')
        self.assertEqual(result['state'],'failed')
        self.assertEqual([r['state'] for r in result['jobs']],['completed','failed'])
