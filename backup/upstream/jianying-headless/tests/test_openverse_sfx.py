"""Openverse sound cues, selection and placement behind a fake network.

No request reaches Openverse or Freesound. Synthetic WAV/MP3 fixtures, compiled
plans, reports and credits are retained under project work/. No app, codec,
user draft or user media is used. Cue compilation and preview decoding need
ffmpeg and ffprobe on PATH; those cases are skipped without them.
"""
from copy import deepcopy
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
import wave

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'skills/yichen-jianying-edit/scripts'))
import edit_plan
import openverse_sfx

WORK = ROOT / 'work/openverse-sfx-tests'
WORK.mkdir(parents=True, exist_ok=True)
FFMPEG = bool(shutil.which('ffmpeg') and shutil.which('ffprobe'))


def make_wave(path, seconds=4):
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(48000)
        out.writeframes(b''.join(struct.pack('<h', int(math.sin(i * 2 * math.pi * 440 / 48000) * 1800))
                                for i in range(int(seconds * 48000))))


def source_plan(path):
    return {'schema': 'jianying-edit-plan/v1', 'source': str(path),
            'source_sha256': edit_plan.digest(path), 'source_duration': 4.0,
            'fps': 30, 'speed': 1.5, 'voice_volume': 1.0,
            'settings_confirmed': True, 'check_decisions_pending': False, 'bgm': False,
            'keeps': [{'start': 0, 'end': 1.5, 'protect': [[0.04, 1.46]]},
                      {'start': 2, 'end': 3.5, 'protect': [[2.04, 3.46]]}],
            'subtitles': [{'start': 0.04, 'end': 1.46, 'text': '前一句👍'},
                          {'start': 2.04, 'end': 3.46, 'text': '后一句'}], 'sfx': []}


def openverse_result(number, title, license, duration=600, tags=()):
    """Synthetic result in the Openverse v1 audio shape; no real creator or recording."""
    version = '1.0' if license == 'cc0' else '4.0'
    return {'id': '%08x-0000-4000-8000-%012x' % (number, number), 'title': title, 'license': license,
            'license_version': version, 'license_url': 'https://creativecommons.org/licenses/%s/%s/' % (license, version),
            'creator': 'creator%d' % number, 'foreign_landing_url': 'https://freesound.org/s/%d/' % number,
            'url': 'https://cdn.freesound.org/previews/%d/%d-hq.mp3' % (number, number), 'duration': duration,
            'tags': [{'name': tag} for tag in tags], 'mature': False, 'attribution': '"%s" by creator%d' % (title, number)}


def make_mp3(path, seconds=0.8):
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-n', '-f', 'lavfi', '-i',
                    'sine=frequency=880:sample_rate=44100:duration=%g' % seconds, '-af',
                    'adelay=delays=100:all=1,volume=0.3', '-c:a', 'libmp3lame', '-b:a', '128k', str(path)], check=True)
    return path.read_bytes()


def write_pcm(path, values):
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(48000)
        out.writeframes(struct.pack('<%dh' % len(values), *values))


def headless_plan(compiled):
    """Track layout written by the engine's from-compiled, without probing a video source."""
    return {'schema': 'jy14-headless-plan/v1', 'name': 'openverse-test',
            'canvas': {'width': 1920, 'height': 1080, 'fps': compiled['fps']},
            'tracks': [{'type': 'video', 'name': '口播', 'segments': [
                {'source': compiled['source'], 'start_us': r['target_start_us'], 'duration_us': r['target_duration_us'],
                 'source_start_us': r['source_start_us'], 'source_duration_us': r['source_duration_us'],
                 'speed': compiled['speed'], 'volume': compiled['voice_volume']} for r in compiled['ranges']]},
                {'type': 'text', 'name': '字幕', 'segments': [
                    {'start_us': s['start_us'], 'duration_us': s['end_us'] - s['start_us'], 'text': s['text']}
                    for s in compiled['subtitles']]}]}


class FakeResponse:
    def __init__(self, url, body, headers):
        self.url, self.body, self.headers = url, body, headers

    def __enter__(self):
        return self

    def __exit__(self, *error):
        return False

    def geturl(self):
        return self.url

    def read(self, limit=-1):
        return self.body if limit < 0 else self.body[:limit]


class FakeOpener:
    """Answers Openverse searches from fixtures, filtered by the requested licenses."""

    def __init__(self, searches, files):
        self.searches, self.files, self.requests = searches, files, []

    def open(self, request, timeout=None):
        url = request.full_url
        self.requests.append(url)
        parts = urllib.parse.urlsplit(url)
        if parts.hostname == 'api.openverse.org':
            query = urllib.parse.parse_qs(parts.query)
            licenses = query['license'][0].split(',')
            results = [r for r in self.searches.get(query['q'][0], []) if r['license'] in licenses]
            return FakeResponse(url, json.dumps({'results': results}).encode(),
                                {'x-ratelimit-available-anon_burst': '18', 'x-ratelimit-available-anon_sustained': '190'})
        return FakeResponse(url, self.files[url], {'Content-Type': 'audio/mpeg'})


class OpenverseSelectionTests(unittest.TestCase):
    """Ranking, leveling and network guards; pure Python, no FFmpeg."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix='case-', dir=WORK))

    def test_ranking_prefers_clean_commercial_safe_matches(self):
        results = [openverse_result(1, 'Pop', 'by-nc'), openverse_result(2, 'Pop music loop', 'cc0'),
                   openverse_result(3, 'Pop sound', 'by'), openverse_result(4, 'pop 2', 'cc0'),
                   openverse_result(5, 'Big pop', 'cc0', duration=9000),
                   dict(openverse_result(6, 'Pop', 'cc0'), url='https://example.com/pop.mp3'),
                   dict(openverse_result(7, 'Pop', 'cc0'), mature=True),
                   openverse_result(8, 'Pop', 'cc0', duration=20), openverse_result(9, 'Thud', 'cc0')]
        ranked, rejected = openverse_sfx.rank(results, 'pop', 1000000, openverse_sfx.DEFAULT_LICENSES)
        self.assertEqual([r['id'][:8] for _, r, _ in ranked], ['00000004', '00000003', '00000005', '00000001', '00000002'])
        self.assertEqual(rejected, {'host': 1, 'sensitive': 1, 'duration': 1, 'no-match': 1})
        ranked, rejected = openverse_sfx.rank(results, 'pop', 1000000, openverse_sfx.COMMERCIAL_LICENSES)
        self.assertNotIn('by-nc', [r['license'] for _, r, _ in ranked])
        self.assertEqual(rejected['license'], 1)

    def test_noncommercial_only_wins_without_a_clean_safe_match(self):
        results = [openverse_result(1, 'Whoosh', 'by-nc'), openverse_result(2, 'Wind ambience loop', 'cc0', tags=['whoosh']),
                   openverse_result(3, 'Door slam', 'cc0')]
        ranked, _ = openverse_sfx.rank(results, 'whoosh', 1000000, openverse_sfx.DEFAULT_LICENSES)
        self.assertEqual([r['license'] for _, r, _ in ranked], ['by-nc', 'cc0'])

    def test_shape_trims_onset_levels_and_fades(self):
        source = self.folder / 'tone.wav'
        write_pcm(source, [0] * 9600 + [int(1000 * math.sin(2 * math.pi * 1000 * i / 48000)) for i in range(96000)])
        info = openverse_sfx.shape(source, self.folder / 'leveled.wav', 500000)
        self.assertEqual((info['duration_us'], info['truncated'], info['onset_trim_ms']), (500000, True, 197))
        self.assertAlmostEqual(info['gain_db'], 13.32, delta=0.05)
        with wave.open(str(self.folder / 'leveled.wav'), 'rb') as audio:
            self.assertEqual((audio.getframerate(), audio.getnchannels(), audio.getnframes()), (48000, 1, 24000))
            data = struct.unpack('<24000h', audio.readframes(24000))
        self.assertEqual((data[0], data[-1]), (0, 0))
        self.assertAlmostEqual(max(abs(v) for v in data) / 1000, 10 ** (13.32 / 20), delta=0.05)
        click = self.folder / 'click.wav'
        write_pcm(click, [0] * 480 + [16000] * 10 + [0] * 4310)
        info = openverse_sfx.shape(click, self.folder / 'click-leveled.wav', 1000000)
        with wave.open(str(self.folder / 'click-leveled.wav'), 'rb') as audio:
            peak = max(abs(v) for v in struct.unpack('<%dh' % audio.getnframes(), audio.readframes(audio.getnframes())))
        self.assertAlmostEqual(info['gain_db'], 5.23, delta=0.01)
        self.assertTrue(29100 <= peak <= 29206)

    def test_shape_rejects_silent_preview(self):
        source = self.folder / 'silence.wav'
        write_pcm(source, [0] * 24000)
        with self.assertRaisesRegex(ValueError, 'silent'):
            openverse_sfx.shape(source, self.folder / 'out.wav', 500000)
        self.assertFalse((self.folder / 'out.wav').exists())

    def test_network_allowlist_and_preview_type(self):
        client = openverse_sfx.Client(opener=FakeOpener({}, {}), sleep=lambda seconds: None)
        for url in ['https://example.com/x.mp3', 'http://cdn.freesound.org/x.mp3']:
            with self.assertRaisesRegex(ValueError, 'allowlist'):
                client.get(url, openverse_sfx.DOWNLOAD_HOSTS, 10, 'audio/mpeg')

        class Redirected:
            def open(self, request, timeout=None):
                return FakeResponse('https://evil.example/x.mp3', b'ID3', {'Content-Type': 'audio/mpeg'})

        with self.assertRaisesRegex(ValueError, 'allowlist'):
            openverse_sfx.Client(opener=Redirected()).get('https://cdn.freesound.org/x.mp3',
                                                          openverse_sfx.DOWNLOAD_HOSTS, 10, 'audio/mpeg')
        item = openverse_result(1, 'Pop', 'cc0')
        work = self.folder / 'net'
        (work / 'downloads').mkdir(parents=True)
        client = openverse_sfx.Client(opener=FakeOpener({}, {item['url']: b'<html></html>'}), sleep=lambda seconds: None)
        with self.assertRaisesRegex(ValueError, 'not an MP3'):
            openverse_sfx.download(client, item, work)
        self.assertFalse(list((work / 'downloads').iterdir()))

    def test_rate_limit_retries_briefly_then_stops(self):
        class Limited:
            def __init__(self, waits):
                self.waits, self.calls = waits, 0

            def open(self, request, timeout=None):
                self.calls += 1
                if self.calls <= len(self.waits):
                    raise urllib.error.HTTPError(request.full_url, 429, 'Too Many Requests',
                                                 {'Retry-After': self.waits[self.calls - 1]}, None)
                return FakeResponse(request.full_url, b'{"results": []}', {})

        sleeps = []
        flaky = Limited(['2'])
        self.assertEqual(openverse_sfx.search(openverse_sfx.Client(opener=flaky, sleep=sleeps.append), 'pop',
                                              openverse_sfx.DEFAULT_LICENSES), [])
        self.assertEqual((flaky.calls, sleeps), (2, [2]))
        daily = Limited(['3600'])
        with self.assertRaisesRegex(RuntimeError, 'rate limit'):
            openverse_sfx.search(openverse_sfx.Client(opener=daily, sleep=sleeps.append), 'pop',
                                 openverse_sfx.DEFAULT_LICENSES)
        self.assertEqual(daily.calls, 1)


@unittest.skipUnless(FFMPEG, 'FFmpeg and ffprobe are required')
class OpenverseCueTests(unittest.TestCase):
    """Speech-time cue compilation and plan augmentation with fake previews."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix='case-', dir=WORK))
        self.source = self.folder / 'source.wav'
        make_wave(self.source)
        self.raw = source_plan(self.source)

    def compile_files(self, sfx):
        self.raw['sfx'] = sfx
        compiled = edit_plan.compile_plan(self.raw)
        edit_plan.validate_compiled(compiled)
        compiled_path = self.folder / 'compiled.json'
        compiled_path.write_text(json.dumps(compiled, ensure_ascii=False))
        plan_path = self.folder / 'headless-plan.json'
        plan_path.write_text(json.dumps(headless_plan(compiled), ensure_ascii=False))
        return compiled, compiled_path, plan_path

    def client(self, searches):
        files = {}
        for results in searches.values():
            for item in results:
                if item['url'] not in files:
                    files[item['url']] = make_mp3(self.folder / (item['id'] + '.mp3'))
        self.opener = FakeOpener(searches, files)
        return openverse_sfx.Client(opener=self.opener, sleep=lambda seconds: None)

    def test_openverse_cue_follows_speech_time_map(self):
        compiled, _, _ = self.compile_files([{'source_time': 2.5, 'openverse': '  Whoosh  Transition ',
                                              'volume': 0.4, 'max_duration': 1.2, 'reason': '转场'}])
        self.assertEqual(compiled['sfx'], [])
        self.assertEqual(compiled['openverse_sfx'], [{'query': 'whoosh transition', 'start_us': 1333333,
                                                      'max_duration_us': 1200000, 'volume': 0.4, 'reason': '转场'}])

    def test_openverse_cue_input_is_checked(self):
        cases = [({'source_time': 0.3, 'openverse': '转场'}, 'English'),
                 ({'source_time': 0.3, 'openverse': 'pop', 'name': '啵1'}, 'either'),
                 ({'source_time': 0.3, 'openverse': 'pop', 'volume': 1.5}, '0-1'),
                 ({'source_time': 0.3, 'openverse': 'pop', 'max_duration': 9}, '0.1-8'),
                 ({'source_time': 3.45, 'openverse': 'pop'}, 'too close'),
                 ({'source_time': 1.8, 'openverse': 'pop'}, 'inside deleted')]
        for event, message in cases:
            self.raw['sfx'] = [event]
            with self.subTest(event=event), self.assertRaisesRegex(ValueError, message):
                edit_plan.compile_plan(self.raw)

    def test_compiled_openverse_cue_is_revalidated(self):
        compiled, _, _ = self.compile_files([{'source_time': 0.3, 'openverse': 'pop'}])
        changed = deepcopy(compiled)
        changed['openverse_sfx'][0]['start_us'] = compiled['duration_us']
        with self.assertRaisesRegex(ValueError, 'outside the timeline'):
            edit_plan.validate_compiled(changed)
        changed = deepcopy(compiled)
        changed['openverse_sfx'][0]['query'] = 'Pop'
        with self.assertRaisesRegex(ValueError, 'normalized'):
            edit_plan.validate_compiled(changed)

    def test_compiled_plan_without_openverse_cues_stays_valid(self):
        # Compiled plans written before this field must keep passing the engine's from-compiled check.
        compiled, _, plan_path = self.compile_files([])
        legacy = deepcopy(compiled)
        del legacy['openverse_sfx']
        edit_plan.validate_compiled(legacy)
        legacy_path = self.folder / 'legacy-compiled.json'
        legacy_path.write_text(json.dumps(legacy, ensure_ascii=False))
        with self.assertRaisesRegex(ValueError, 'no Openverse sound cues'):
            openverse_sfx.add(legacy_path, plan_path, self.folder / 'out.json', self.folder / 'openverse',
                              client=self.client({}))
        self.assertFalse((self.folder / 'out.json').exists() or (self.folder / 'openverse').exists())

    def test_add_places_cues_and_reports_licenses(self):
        _, compiled_path, plan_path = self.compile_files([
            {'source_time': 0.3, 'openverse': 'pop', 'volume': 0.5, 'max_duration': 0.5},
            {'source_time': 2.5, 'openverse': 'pop', 'volume': 0.5, 'max_duration': 0.5},
            {'source_time': 2.6, 'openverse': 'whoosh', 'volume': 0.3, 'max_duration': 1.0}])
        client = self.client({'pop': [openverse_result(1, 'Pop', 'by-nc'), openverse_result(2, 'pop 2', 'cc0')],
                              'whoosh': [openverse_result(3, 'Whoosh', 'by-nc', tags=['swoosh']),
                                         openverse_result(4, 'Wind ambience loop', 'cc0', tags=['whoosh'])]})
        out, work = self.folder / 'plan-sfx.json', self.folder / 'openverse'
        summary = openverse_sfx.add(compiled_path, plan_path, out, work, client=client)
        self.assertEqual((summary['cues'], summary['sounds'], summary['tracks']), (3, 2, 2))
        self.assertEqual(summary['licenses'], {'cc0': 1, 'by': 0, 'by-nc': 1})
        self.assertTrue(summary['noncommercial_used'] and summary['attribution_required'])
        self.assertEqual(sum('api.openverse.org' in url for url in self.opener.requests), 2)
        plan = json.loads(out.read_text())
        tracks = [t for t in plan['tracks'] if t['name'].startswith('Openverse')]
        self.assertEqual([[s['start_us'] for s in t['segments']] for t in tracks], [[200000, 1333333], [1400000]])
        self.assertEqual([[s['volume'] for s in t['segments']] for t in tracks], [[0.5, 0.5], [0.3]])
        self.assertEqual([s['duration_us'] for s in tracks[0]['segments']], [500000, 500000])
        self.assertEqual(tracks[1]['segments'][0]['duration_us'], 600000)  # clamped to the video end
        for segment in tracks[0]['segments'] + tracks[1]['segments']:
            self.assertGreaterEqual(openverse_sfx.probe_us(segment['source']), segment['duration_us'])
        notice = (work / 'credits.md').read_text()
        self.assertIn('CC BY-NC（禁止商用）', notice)
        self.assertIn('“Whoosh” by creator3', notice)
        self.assertIn('| 00:00.2 | pop | pop 2 |', notice)
        report = json.loads((work / 'report.json').read_text())
        self.assertEqual((report['status'], len(report['placements'])), ('added', 3))

    def test_commercial_mode_fails_closed_without_safe_match(self):
        _, compiled_path, plan_path = self.compile_files([{'source_time': 2.6, 'openverse': 'whoosh'}])
        client = self.client({'whoosh': [openverse_result(3, 'Whoosh', 'by-nc'), openverse_result(4, 'Door slam', 'cc0')]})
        out, work = self.folder / 'plan-sfx.json', self.folder / 'openverse'
        with self.assertRaisesRegex(RuntimeError, 'No usable Openverse sound for "whoosh"'):
            openverse_sfx.add(compiled_path, plan_path, out, work, commercial=True, client=client)
        report = json.loads((work / 'report.json').read_text())
        self.assertEqual((report['status'], report['allowed_licenses']), ('failed', ['cc0', 'by']))
        self.assertIn('license=cc0%2Cby&', self.opener.requests[0])
        self.assertFalse(out.exists())

    def test_plan_must_match_compiled_and_not_be_augmented_twice(self):
        _, compiled_path, plan_path = self.compile_files([{'source_time': 0.3, 'openverse': 'pop'}])
        plan = json.loads(plan_path.read_text())
        plan['tracks'].append({'type': 'audio', 'name': 'Openverse 音效 1', 'segments': []})
        twice = self.folder / 'twice.json'
        twice.write_text(json.dumps(plan))
        with self.assertRaisesRegex(ValueError, 'already has Openverse'):
            openverse_sfx.add(compiled_path, twice, self.folder / 'out-1.json', self.folder / 'work-1', client=self.client({}))
        plan = json.loads(plan_path.read_text())
        plan['tracks'][0]['segments'][-1]['duration_us'] -= 1000
        short = self.folder / 'short.json'
        short.write_text(json.dumps(plan))
        with self.assertRaisesRegex(ValueError, 'timeline length'):
            openverse_sfx.add(compiled_path, short, self.folder / 'out-2.json', self.folder / 'work-2', client=self.client({}))
        self.assertFalse((self.folder / 'work-1').exists() or (self.folder / 'work-2').exists())


if __name__ == '__main__':
    unittest.main()
