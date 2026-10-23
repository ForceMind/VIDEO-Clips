#!/usr/bin/env python3
"""Generate synthetic media + fixture AI decisions, then exercise the real CLI.

No model or ASR network calls. This is reproducible functional evidence, not an
AI-quality benchmark. All generated media are independent synthetic fixtures.
"""
from __future__ import annotations
import argparse
import contextlib
import io
import json
from pathlib import Path
import subprocess
from video_clips.agent import AGENT_SCHEMA
from video_clips.cli import main
from video_clips.editorial import transcript_sha256
from video_clips.pipeline import file_sha256
from video_clips.plan import Caption
from video_clips.subtitles import write_srt


def generate(folder):
    root=Path(folder).expanduser().resolve();root.mkdir(parents=True,exist_ok=False)
    source=root/'source.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=640x360:rate=25:duration=6',
        '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=6',
        '-c:v','libx264','-threads','2','-c:a','aac','-shortest',str(source)],check=True,timeout=30)
    cues=[Caption('VIDEO-Clips runs locally.',200,1200),Caption('Um, let me start again.',1800,700),
          Caption('Keep the important context.',2900,1100),Caption('Revenue increased by 12%.',4400,1100)]
    srt=write_srt(cues,root/'source.srt')
    response={'schema':AGENT_SCHEMA,'transcript_sha256':transcript_sha256(cues),
        'decisions':[{'cue':i,'text':c.text,'action':'EXCLUDE' if i==2 else 'KEEP',
            'reason':'Standalone hesitation' if i==2 else 'Preserves key meaning and context',
            'category':'filler' if i==2 else 'important','confidence':.99,'duplicate_of':None}
            for i,c in enumerate(cues,1)]}
    reply=root/'fixture-agent-response.json';reply.write_text(json.dumps(response,indent=2),encoding='utf-8')
    before=file_sha256(source)
    with contextlib.redirect_stdout(io.StringIO()) as captured:
        code=main(['auto-edit',str(source),'--srt',str(srt),'--instruction','Remove hesitations; preserve context',
            '--strategy','standard','--protect-term','VIDEO-Clips','--response',str(reply),
            '--apply-ai-cuts','--workdir',str(root/'job'),'--render'])
    if code:raise RuntimeError('CLI smoke failed')
    assert before==file_sha256(source),'original source changed'
    result=json.loads(captured.getvalue());assert result['applied_cuts']==1,result
    evidence={'mode':'synthetic media with fixture model reply; no ASR/model API calls',
        'source_sha256':before,'source_unchanged':True,'output_sha256':file_sha256(root/'job'/'output.mp4'),
        'result':result,'quality':json.loads((root/'job'/'quality.json').read_text())}
    (root/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(evidence,indent=2))
    return evidence


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True)
    generate(parser.parse_args().out)
