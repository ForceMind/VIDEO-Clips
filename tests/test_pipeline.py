import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_agent import response_for
from test_llm import CompatibleServer
from video_clips.agent import AgentOptions
from video_clips.cli import main
from video_clips.pipeline import run_agent_pipeline, file_sha256
from video_clips.plan import Caption, load_plan
from video_clips.subtitles import write_srt


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg unavailable')
class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root/'source.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x240:rate=25:duration=4',
                        '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=4',
                        '-c:v','libx264','-threads','2','-c:a','aac','-shortest',str(self.source)],
                        check=True,capture_output=True,timeout=30)
        self.cues = [Caption('Core idea',200,600), Caption('Um',1200,600), Caption('Result is 12%',2400,800)]
        self.payload = response_for(self.cues)
        self.payload['decisions'][1].update(action='EXCLUDE', category='filler', reason='Standalone hesitation')
        self.response = self.root/'response.json'; self.response.write_text(json.dumps(self.payload))
        self.srt = write_srt(self.cues, self.root/'source.srt')
        self.job = self.root/'job'
        self.options = AgentOptions('Remove hesitations', target_ms=1000, apply_cuts=True)

    def test_real_http_agent_to_ffmpeg_and_resume_without_second_model_call(self):
        before = file_sha256(self.source)
        with CompatibleServer() as server:
            server.reply = self.payload
            with patch('video_clips.pipeline.render', side_effect=RuntimeError('simulated renderer interruption')):
                with self.assertRaisesRegex(RuntimeError, 'interruption'):
                    run_agent_pipeline(self.source, self.cues, self.job, self.options, model=server.config,
                        allow_paid=True, render_output=True)
            self.assertEqual(json.loads((self.job/'job.json').read_text())['stage'], 'failed')
            result = run_agent_pipeline(self.source, self.cues, self.job, self.options, model=server.config,
                render_output=True, resume=True)
            self.assertEqual(len(server.calls), 1)
        self.assertEqual(result['stage'], 'completed')
        self.assertEqual(result['applied_cuts'], 1)
        self.assertFalse(result['target_met'])
        self.assertTrue((self.job/'output.mp4').is_file())
        plan = load_plan(self.job/'plan.json')
        self.assertEqual([c.text for c in plan.captions], ['Core idea','Result is 12%'])
        self.assertEqual(before, file_sha256(self.source))
        manifest = json.loads((self.job/'job.json').read_text())
        self.assertEqual(manifest['output_sha256'], file_sha256(self.job/'output.mp4'))
        for clip in plan.videos:
            self.assertFalse(clip.source_start_ms < 1800 and clip.source_start_ms+clip.duration_ms > 1200)

    def test_cli_offline_review_then_reject_changed_job(self):
        args = ['auto-edit',str(self.source),'--srt',str(self.srt),'--instruction','Edit',
                '--response',str(self.response),'--workdir',str(self.job)]
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(args), 0)
        self.assertEqual(json.loads(output.getvalue())['applied_cuts'], 0)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 2)
            self.assertEqual(main(args+['--resume','--apply-ai-cuts']), 2)
        self.assertEqual(json.loads((self.job/'job.json').read_text())['stage'], 'planned')

    def test_invalid_timestamps_fail_before_any_model_request(self):
        with CompatibleServer() as server:
            with self.assertRaises(ValueError):
                run_agent_pipeline(self.source,[Caption('past end',8000,500)],self.job,self.options,
                                   model=server.config,allow_paid=True)
            self.assertEqual(server.calls, [])
            self.assertFalse(self.job.exists())

    def test_active_job_is_not_resumed(self):
        run_agent_pipeline(self.source,self.cues,self.job,self.options,response_file=self.response)
        (self.job/'.running').write_text('active')
        with self.assertRaises(FileExistsError):
            run_agent_pipeline(self.source,self.cues,self.job,self.options,response_file=self.response,resume=True)
        self.assertTrue((self.job/'.running').exists())
