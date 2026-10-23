"""Authenticated loopback application backed by the real local Agent/render pipeline."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import copy
import json
import mimetypes
import re
import secrets
import threading
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
import uuid

from .agent import AgentOptions, strict_json
from .editorial import make_editorial_brief
from .jianying import export_plan
from .llm import ModelConfig
from .pipeline import atomic_json, run_agent_pipeline
from .plan import Caption, load_plan
from .subtitles import parse_srt
from .timed_asr import captions_from_step_file

MEDIA = {'.mp4','.mov','.mkv','.webm','.m4v','.avi','.wav','.mp3','.ogg','.opus','.m4a','.png','.jpg','.jpeg','.webp'}
IMPORTS = MEDIA | {'.srt','.json'}
ID = re.compile(r'^[a-f0-9]{32}$')
ARTIFACTS = {'video':'output.mp4','srt':'captions.srt','plan':'plan.json',
             'review':'review.json','quality':'quality.json','jianying':'jianying-plan.json'}


class LocalApp:
    def __init__(self, workspace):
        self.root = Path(workspace).expanduser().resolve(strict=True)
        if not self.root.is_dir(): raise ValueError('workspace must be a directory')
        self.jobs = self.root/'.video-clips'/'jobs'
        if (self.root/'.video-clips').is_symlink() or self.jobs.is_symlink():
            raise ValueError('job storage cannot be a symlink')
        self.jobs.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_urlsafe(32)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='video-clips')
        self.mutex = threading.Lock()
        self.active = set()

    def close(self):
        self.executor.shutdown(wait=True)

    def local(self, name, *, suffixes=None):
        if not isinstance(name,str) or not name or '\0' in name:
            raise ValueError('choose a workspace file')
        candidate = self.root/name
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self.root): raise ValueError('path leaves workspace')
        resolved = candidate.resolve(strict=True)
        # Refuse symlinks in every workspace-relative component.
        cursor = candidate
        while cursor != self.root:
            if cursor.is_symlink(): raise ValueError('symlinks are not permitted')
            if cursor.parent == cursor: raise ValueError('invalid workspace path')
            cursor = cursor.parent
        if suffixes and (not resolved.is_file() or resolved.suffix.lower() not in suffixes):
            raise ValueError('unsupported workspace file type')
        return resolved

    def list_files(self, directory='.'):
        folder = self.local(directory)
        if not folder.is_dir(): raise ValueError('not a directory')
        entries=[]
        for path in sorted(folder.iterdir(),key=lambda p:(not p.is_dir(),p.name.casefold())):
            if path.name.startswith('.') or path.is_symlink(): continue
            if path.is_dir() or path.suffix.lower() in IMPORTS:
                entries.append({'path':path.relative_to(self.root).as_posix(),'name':path.name,
                    'directory':path.is_dir(),'size':path.stat().st_size if path.is_file() else 0,
                    'suffix':path.suffix.lower()})
            if len(entries)>=500: break
        return {'directory':folder.relative_to(self.root).as_posix(),'files':entries}

    def transcript(self, path):
        source = self.local(path,suffixes={'.srt','.json'})
        if source.stat().st_size>4*1024*1024: raise ValueError('transcript exceeds 4 MiB')
        text=source.read_text(encoding='utf-8-sig')
        cues = parse_srt(text) if source.suffix.lower()=='.srt' else captions_from_step_file(strict_json(text))
        make_editorial_brief(cues)
        return [asdict(c) for c in cues]

    def status(self, job_id):
        if not ID.fullmatch(job_id): raise ValueError('invalid job id')
        status_path = self.jobs/f'{job_id}.status.json'
        if not status_path.is_file(): raise FileNotFoundError('job not found')
        status = strict_json(status_path.read_text(encoding='utf-8'))
        manifest=self.jobs/job_id/'job.json'
        if manifest.is_file() and status['state']=='running':
            status['stage']=strict_json(manifest.read_text(encoding='utf-8')).get('stage')
        if status['state'] in {'queued','running'} and job_id not in self.active:
            status.update(state='interrupted',stage='interrupted')
        return status

    def list_jobs(self):
        return [self.status(p.name.split('.')[0]) for p in
                sorted(self.jobs.glob('*.status.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:100]]

    def submit(self, payload):
        if not isinstance(payload,dict): raise ValueError('job must be an object')
        source = self.local(payload.get('source'),suffixes=MEDIA-{'.wav','.mp3','.ogg','.opus','.m4a','.png','.jpg','.jpeg','.webp'})
        raw_cues=payload.get('cues')
        if not isinstance(raw_cues,list) or not 1<=len(raw_cues)<=1000: raise ValueError('import a timed transcript first')
        cues=[]
        for raw in raw_cues:
            if not isinstance(raw,dict) or set(raw)!={'text','start_ms','duration_ms'}: raise ValueError('invalid transcript cue')
            if (not isinstance(raw['text'],str) or type(raw['start_ms']) is not int or
                    type(raw['duration_ms']) is not int): raise ValueError('invalid cue text/timestamp')
            cues.append(Caption(**raw))
        make_editorial_brief(cues)
        if not isinstance(payload.get('protected_terms',[]),list): raise ValueError('protected terms must be a list')
        options=AgentOptions(payload.get('instruction',''),payload.get('strategy','standard'),
            payload.get('target_ms'),tuple(payload.get('protected_terms',[])),payload.get('apply_cuts',False))
        options.validate()
        aspect=payload.get('aspect','source')
        if aspect not in {'source','16:9','9:16','1:1'}: raise ValueError('invalid aspect')
        response_path = self.local(payload['response'],suffixes={'.json'}) if payload.get('response') else None
        model=None
        if not response_path:
            model=ModelConfig(payload.get('endpoint',''),payload.get('model',''))
            model.validate()
        allow_paid=payload.get('allow_paid',False)
        if type(allow_paid) is not bool: raise ValueError('allow_paid must be boolean')
        if model and not allow_paid: raise ValueError('explicit model request consent required')
        music = self.local(payload['music'],suffixes=MEDIA) if payload.get('music') else None
        music_volume = payload.get('music_volume',.15)
        if type(music_volume) not in (int,float) or not 0<=music_volume<=2: raise ValueError('music volume must be 0..2')
        config={'source':str(source),'cues':[asdict(c) for c in cues],'options':asdict(options),
            'model':asdict(model) if model else None,'response_file':str(response_path) if response_path else None,
            'allow_paid':allow_paid,'aspect':aspect,'music':str(music) if music else None,'music_volume':music_volume}
        # Collapse identical in-flight clicks; a completed re-run is an explicit new job.
        with self.mutex:
            for job_id in self.active:
                old=strict_json((self.jobs/f'{job_id}.config.json').read_text(encoding='utf-8'))
                if old==config: return self.status(job_id)
            job_id=uuid.uuid4().hex
            atomic_json(self.jobs/f'{job_id}.config.json',config)
            return self._queue(job_id,config,resume=False)

    def _queue(self, job_id, config, *, resume):
        status={'id':job_id,'state':'queued','stage':'queued','source':Path(config['source']).name}
        self.active.add(job_id)
        atomic_json(self.jobs/f'{job_id}.status.json',status)
        self.executor.submit(self._execute,job_id,config,resume)
        return status

    def _execute(self, job_id, config, resume):
        path=self.jobs/f'{job_id}.status.json'
        status={'id':job_id,'state':'running','stage':'preparing','source':Path(config['source']).name}
        atomic_json(path,status)
        try:
            result=run_agent_pipeline(config['source'],[Caption(**r) for r in config['cues']],self.jobs/job_id,
                AgentOptions(**config['options']),model=ModelConfig(**config['model']) if config['model'] else None,
                response_file=config['response_file'],allow_paid=config['allow_paid'],render_output=True,
                aspect=config['aspect'],resume=resume,music=config['music'],music_volume=config['music_volume'])
            status.update(state='completed',stage='completed',result=result)
        except Exception as exc:
            status.update(state='failed',stage='failed',error=str(exc)[:500])
        finally:
            atomic_json(path,status)
            with self.mutex: self.active.discard(job_id)

    def resume(self, job_id):
        with self.mutex:
            state=self.status(job_id)
            if job_id in self.active: return state
            if state['state']=='completed': return state
            config=strict_json((self.jobs/f'{job_id}.config.json').read_text(encoding='utf-8'))
            return self._queue(job_id,config,resume=(self.jobs/job_id/'job.json').is_file())

    def detail(self, job_id):
        result={'status':self.status(job_id)}
        config=strict_json((self.jobs/f'{job_id}.config.json').read_text(encoding='utf-8'))
        result['input']={**config,'source':Path(config['source']).relative_to(self.root).as_posix(),
            'music':Path(config['music']).relative_to(self.root).as_posix() if config['music'] else None,
            'response_file':Path(config['response_file']).relative_to(self.root).as_posix() if config['response_file'] else None}
        for key,name in [('review','review.json'),('plan','plan.json'),('quality','quality.json')]:
            path=self.jobs/job_id/name
            result[key]=strict_json(path.read_text(encoding='utf-8')) if path.is_file() else None
        return result

    def review(self, job_id, excluded):
        status=self.status(job_id)
        if status['state']!='completed': raise ValueError('wait for job completion before reviewing')
        root=self.jobs/job_id
        original=strict_json((root/'agent-response.json').read_text(encoding='utf-8'))
        if not isinstance(excluded,list) or any(type(i) is not int for i in excluded) or len(set(excluded))!=len(excluded):
            raise ValueError('excluded cues must be unique integer cue numbers')
        eligible={r['cue'] for r in original['decisions'] if r['action']=='EXCLUDE'}
        if not set(excluded)<=eligible: raise ValueError('only proposed exclusions can be approved')
        revised=copy.deepcopy(original)
        for row in revised['decisions']:
            if row['action']=='EXCLUDE' and row['cue'] not in excluded:
                row.update(action='KEEP',reason='Restored by reviewer',category='context',duplicate_of=None)
        # A child job gives a reversible version without changing any original output.
        reply=root/('review-'+uuid.uuid4().hex+'.json')
        atomic_json(reply,revised)
        config=strict_json((self.jobs/f'{job_id}.config.json').read_text(encoding='utf-8'))
        config.update(response_file=str(reply),model=None,allow_paid=False)
        config['options']['apply_cuts']=True
        with self.mutex:
            new_id=uuid.uuid4().hex
            atomic_json(self.jobs/f'{new_id}.config.json',config)
            return self._queue(new_id,config,resume=False)

    def artifact(self, job_id, kind):
        self.status(job_id)
        if kind not in ARTIFACTS: raise ValueError('unknown artifact type')
        path=self.jobs/job_id/ARTIFACTS[kind]
        if kind=='jianying' and not path.exists(): export_plan(load_plan(self.jobs/job_id/'plan.json'),path)
        if not path.is_file(): raise FileNotFoundError('artifact is not available yet')
        return path


def make_server(app: LocalApp, *, port=8765):
    if type(port) is not int or not 0<=port<=65535: raise ValueError('port must be 0..65535')
    class Handler(BaseHTTPRequestHandler):
        server_version='VIDEO-Clips'
        def log_message(self,*args): pass  # Do not log tokens, paths or transcript content.
        def _headers(self,code,content_type,length,extra=None):
            self.send_response(code)
            for key,value in {'Content-Type':content_type,'Content-Length':str(length),'Cache-Control':'no-store',
                'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer',
                'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'",**(extra or {})}.items():
                self.send_header(key,value)
            self.end_headers()
        def _json(self,payload,code=200):
            body=json.dumps(payload,ensure_ascii=False).encode()
            self._headers(code,'application/json; charset=utf-8',len(body));self.wfile.write(body)
        def _authorized(self,query):
            expected=f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host')!=expected: raise PermissionError('invalid local host')
            origin=self.headers.get('Origin')
            if origin and origin!='http://'+expected: raise PermissionError('cross-origin requests denied')
            token=self.headers.get('X-Video-Clips-Token','')
            if not token and self.command=='GET' and urlsplit(self.path).path in {'/api/media','/api/artifact'}:
                token=query.get('token',[''])[0]
            if not secrets.compare_digest(token,app.token): raise PermissionError('session token required')
        def _body(self):
            size=int(self.headers.get('Content-Length','0'))
            if not 1<=size<=1024*1024: raise ValueError('JSON request must be 1 byte..1 MiB')
            payload=strict_json(self.rfile.read(size).decode('utf-8'))
            if not isinstance(payload,dict): raise ValueError('request must be an object')
            return payload
        def _file(self,path):
            size=path.stat().st_size; start=0;end=size-1;code=200
            range_header=self.headers.get('Range')
            if range_header:
                match=re.fullmatch(r'bytes=(\d*)-(\d*)',range_header)
                if not match or not any(match.groups()): raise ValueError('unsupported byte range')
                a,b=match.groups()
                if a:
                    start=int(a);end=min(int(b),end) if b else end
                else: start=max(0,size-int(b))
                if start>end or start>=size:
                    self._headers(416,'text/plain',0,{'Content-Range':f'bytes */{size}'});return
                code=206
            extra={'Accept-Ranges':'bytes'}
            if code==206: extra['Content-Range']=f'bytes {start}-{end}/{size}'
            self._headers(code,mimetypes.guess_type(path.name)[0] or 'application/octet-stream',end-start+1,extra)
            with path.open('rb') as stream:
                stream.seek(start);remaining=end-start+1
                while remaining:
                    chunk=stream.read(min(1024*1024,remaining))
                    if not chunk:break
                    self.wfile.write(chunk);remaining-=len(chunk)
        def _handle(self,post=False):
            parsed=urlsplit(self.path);query=parse_qs(parsed.query);route=parsed.path
            try:
                if not post and route in {'/','/app.js','/style.css'}:
                    asset={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[route]
                    body=files('video_clips').joinpath('web').joinpath(asset).read_bytes()
                    mime={'index.html':'text/html; charset=utf-8','app.js':'text/javascript; charset=utf-8','style.css':'text/css; charset=utf-8'}[asset]
                    self._headers(200,mime,len(body));self.wfile.write(body);return
                self._authorized(query)
                if not post:
                    if route=='/api/files': return self._json(app.list_files(query.get('directory',['.'])[0]))
                    if route=='/api/jobs': return self._json(app.list_jobs())
                    if route=='/api/job': return self._json(app.detail(query.get('id',[''])[0]))
                    if route=='/api/media': return self._file(app.local(query.get('path',[''])[0],suffixes=MEDIA))
                    if route=='/api/artifact': return self._file(app.artifact(query.get('id',[''])[0],query.get('kind',[''])[0]))
                elif route=='/api/upload':
                    name=Path(unquote(query.get('name',[''])[0]).replace('\\','/')).name
                    suffix=Path(name).suffix.lower()
                    size=int(self.headers.get('Content-Length','0'))
                    if suffix not in IMPORTS or not 1<=size<=2*1024**3: raise ValueError('unsupported import type or size (limit 2 GiB)')
                    folder=app.root/'imports';folder.mkdir(exist_ok=True)
                    if folder.is_symlink(): raise ValueError('imports directory cannot be a symlink')
                    safe_name=re.sub(r'[^\w.\-]','_',name)[:120]
                    target=folder/(uuid.uuid4().hex[:10]+'-'+safe_name)
                    try:
                        with target.open('xb') as stream:
                            remaining=size
                            while remaining:
                                chunk=self.rfile.read(min(1024*1024,remaining))
                                if not chunk: raise ValueError('incomplete upload')
                                stream.write(chunk);remaining-=len(chunk)
                    except Exception:
                        target.unlink(missing_ok=True);raise
                    return self._json({'path':target.relative_to(app.root).as_posix()})
                else:
                    body=self._body()
                    if route=='/api/transcript': return self._json({'cues':app.transcript(body.get('path'))})
                    if route=='/api/jobs': return self._json(app.submit(body),202)
                    if route=='/api/resume': return self._json(app.resume(body.get('id','')),202)
                    if route=='/api/review': return self._json(app.review(body.get('id',''),body.get('excluded')),202)
                return self._json({'error':'not found'},404)
            except PermissionError as exc:self._json({'error':str(exc)},403)
            except FileNotFoundError as exc:self._json({'error':str(exc)},404)
            except (ValueError,OSError,RuntimeError,TypeError) as exc:self._json({'error':str(exc)[:500]},400)
        def do_GET(self):
            try:self._handle()
            except (BrokenPipeError,ConnectionResetError):pass
        def do_POST(self):
            try:self._handle(post=True)
            except (BrokenPipeError,ConnectionResetError):pass
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def serve(workspace, *, port=8765):
    app=LocalApp(workspace);server=make_server(app,port=port)
    print(f'VIDEO-Clips local UI: http://127.0.0.1:{server.server_port}/#{app.token}',flush=True)
    print('This session URL grants access to the selected local workspace. Keep it private.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();app.close()
