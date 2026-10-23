import contextlib
import json
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from test_agent import response_for
from video_clips.local_ui import LocalApp, make_server
from video_clips.plan import Caption
from video_clips.pipeline import file_sha256


class LocalSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.app=LocalApp(self.root);self.addCleanup(self.app.close)
        self.server=make_server(self.app,port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.stop)
        self.url=f'http://127.0.0.1:{self.server.server_port}'
    def stop(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def req(self,path,body=None,*,token=True,headers=None):
        h={'X-Video-Clips-Token':self.app.token} if token else {}
        h.update(headers or {})
        data=json.dumps(body).encode() if body is not None else None
        if data:h['Content-Type']='application/json'
        return urlopen(Request(self.url+path,data=data,headers=h),timeout=30)
    def test_auth_host_origin_and_workspace_containment(self):
        for headers in [{},{'X-Video-Clips-Token':self.app.token,'Origin':'https://other.invalid'},
                        {'X-Video-Clips-Token':self.app.token,'Host':'other.invalid'}]:
            with self.assertRaises(HTTPError) as err:self.req('/api/files',token=False,headers=headers)
            self.assertEqual(err.exception.code,403)
        with self.req('/api/files') as r:self.assertIn('files',json.load(r))
        with self.assertRaises(ValueError):self.app.local('../outside')
        with self.assertRaises(ValueError):self.app.local('/etc/passwd')
        with self.req('/') as r:
            self.assertIn(b'VIDEO-Clips',r.read())
            self.assertIn("frame-ancestors 'none'",r.headers['Content-Security-Policy'])
    def test_range_reads_and_invalid_range(self):
        (self.root/'video.mp4').write_bytes(b'0123456789')
        with self.req('/api/media?path=video.mp4',headers={'Range':'bytes=2-5'}) as r:
            self.assertEqual(r.status,206);self.assertEqual(r.read(),b'2345')
            self.assertEqual(r.headers['Content-Range'],'bytes 2-5/10')
        with self.req('/api/media?path=video.mp4',headers={'Range':'bytes=-3'}) as r:self.assertEqual(r.read(),b'789')
        with self.assertRaises(HTTPError) as err:self.req('/api/media?path=video.mp4',headers={'Range':'bytes=20-'})
        self.assertEqual(err.exception.code,416)
    def test_upload_and_symlink_escape_rejected(self):
        request=Request(self.url+'/api/upload?name=speech.srt',data=b'1\n00:00:00,100 --> 00:00:00,500\nHello\n',
            headers={'X-Video-Clips-Token':self.app.token,'Content-Type':'application/octet-stream'})
        with urlopen(request) as r:path=json.load(r)['path']
        with self.req('/api/transcript',{'path':path}) as r:
            self.assertEqual(json.load(r)['cues'][0]['text'],'Hello')
        with tempfile.TemporaryDirectory() as external:
            outside=Path(external)/'escape.srt';outside.write_text('secret')
            try:(self.root/'escape.srt').symlink_to(outside)
            except OSError:self.skipTest('symlinks unavailable')
            with self.assertRaises(ValueError):self.app.local('escape.srt')
    def test_bad_transcript_is_not_a_background_crash(self):
        with self.assertRaises(HTTPError) as err:self.req('/api/jobs',{'source':None})
        self.assertEqual(err.exception.code,400)
        self.assertEqual(self.app.list_jobs(),[])


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg unavailable')
class LocalWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.app=LocalApp(self.root);self.addCleanup(self.app.close)
        source=self.root/'source.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x240:rate=25:duration=4',
            '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=4','-c:v','libx264',
            '-threads','2','-c:a','aac','-shortest',str(source)],capture_output=True,check=True)
        cues=[Caption('Main idea',200,600),Caption('Um',1200,600),Caption('Result is 12%',2400,800)]
        self.reply=response_for(cues)
        self.reply['decisions'][1].update(action='EXCLUDE',category='filler',reason='Verbal hesitation')
        (self.root/'reply.json').write_text(json.dumps(self.reply))
        self.body={'source':'source.mp4','cues':[{'text':c.text,'start_ms':c.start_ms,'duration_ms':c.duration_ms} for c in cues],
            'instruction':'Remove hesitations','response':'reply.json','apply_cuts':False}
    def wait_for(self,job_id):
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            status=self.app.status(job_id)
            if status['state'] not in {'queued','running'}:return status
            time.sleep(.05)
        self.fail('background job timed out')
    def test_real_background_render_review_and_restoration_create_new_versions(self):
        source_hash=file_sha256(self.root/'source.mp4')
        job=self.app.submit(self.body);self.assertIn(job['state'],['queued','running'])
        result=self.wait_for(job['id']);self.assertEqual(result['state'],'completed',result)
        before=self.app.detail(job['id'])
        self.assertEqual(len(before['plan']['captions']),3)
        child=self.app.review(job['id'],[2]);self.assertNotEqual(job['id'],child['id'])
        result=self.wait_for(child['id']);self.assertEqual(result['state'],'completed',result)
        after=self.app.detail(child['id']);self.assertEqual(len(after['plan']['captions']),2)
        restored=self.app.review(child['id'],[])
        result=self.wait_for(restored['id']);self.assertEqual(result['state'],'completed',result)
        self.assertEqual(len(self.app.detail(restored['id'])['plan']['captions']),3)
        self.assertEqual(len(self.app.detail(job['id'])['plan']['captions']),3)
        self.assertTrue(after['quality']['decode_verified'])
        self.assertTrue(self.app.artifact(child['id'],'jianying').is_file())
        self.assertEqual(file_sha256(self.root/'source.mp4'),source_hash)
        self.assertEqual(self.app.resume(restored['id'])['state'],'completed')
    def test_bgm_is_connected_to_real_plan(self):
        self.body.update(music='source.mp4',music_volume=.12,apply_cuts=True)
        job=self.app.submit(self.body);result=self.wait_for(job['id'])
        self.assertEqual(result['state'],'completed',result)
        plan=self.app.detail(job['id'])['plan'];self.assertEqual(plan['audio'][0]['volume'],.12)
        self.assertEqual(plan['audio'][0]['duration_ms'],max(c['start_ms']+c['duration_ms'] for c in plan['video']))
