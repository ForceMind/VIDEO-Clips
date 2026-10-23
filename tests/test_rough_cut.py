"""Rough-cut compiler must preserve timings and never hide editorial decisions."""
import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from video_clips.cli import main
from video_clips.plan import Caption, load_plan
from video_clips.rough_cut import RoughCutError, compile_rough_cut, read_cut_decisions, video_metadata


class RoughCutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / 'clip.mp4'
        self.video.write_bytes(b'placeholder for plan validation')
        self.cues = (Caption('Hello', 500, 800), Caption('World', 2600, 900))

    def compile(self, cues=None, **options):
        kwargs = dict(duration_ms=5000, width=320, height=240, fps=25,
                      padding_before_ms=100, padding_after_ms=100, merge_gap_ms=400)
        kwargs.update(options)
        return compile_rough_cut(self.video, self.cues if cues is None else cues, **kwargs)

    def test_cut_gaps_and_remap_original_timed_captions(self):
        plan, report = self.compile()
        self.assertEqual(len(plan['video']), 2)
        self.assertEqual([c['source_start_ms'] for c in plan['video']], [400, 2480])
        self.assertEqual([c['start_ms'] for c in plan['captions']], [100, 1120])
        self.assertEqual([c['text'] for c in plan['captions']], ['Hello', 'World'])
        self.assertEqual(report['output_duration_ms'], 2120)
        self.assertEqual(len(report['removed_ranges']), 3)
        self.assertIn('NOT confirmed silence', report['warnings'][0])
        self.assertEqual(report['kept_ranges'][1]['output_start_ms'], 1000)

    def test_short_gap_merges_without_deleting_speech(self):
        plan, report = self.compile((Caption('a', 100, 400), Caption('b', 720, 250)))
        self.assertEqual(len(plan['video']), 1)
        self.assertEqual(len(plan['captions']), 2)
        self.assertEqual(report['included_cues'], [1, 2])

    def test_frame_quantization_is_stable(self):
        plan, report = self.compile((Caption('a', 333, 222),), fps=30)
        self.assertEqual(plan['video'][0]['source_start_ms'], 200)
        self.assertEqual(plan['video'][0]['duration_ms'], 467)
        self.assertEqual(plan['captions'][0]['start_ms'], 133)
        self.assertEqual(plan['captions'][0]['duration_ms'], 222)
        self.assertEqual(report['output_duration_ms'], 467)

    def test_reasoned_exclusion_never_leaks_across_merged_ranges(self):
        cues = [Caption('Intro', 100, 400), Caption('duplicate', 900, 300),
                Caption('Finish', 1500, 400)]
        plan, report = self.compile(cues, exclude={2: 'repeated line'}, merge_gap_ms=5000)
        self.assertEqual(len(plan['video']), 2)
        self.assertEqual([c['text'] for c in plan['captions']], ['Intro', 'Finish'])
        self.assertEqual(report['excluded_cues'][0]['cue'], 2)
        self.assertLessEqual(plan['video'][0]['source_start_ms'] + plan['video'][0]['duration_ms'], 900)
        self.assertGreaterEqual(plan['video'][1]['source_start_ms'], 1200)

    def test_numeric_cue_protected_by_default(self):
        cues = [Caption('before', 100, 300), Caption('涨了 12%', 900, 350), Caption('after', 1800, 300)]
        with self.assertRaisesRegex(RoughCutError, 'numerical content'):
            self.compile(cues, exclude={2: 'AI thinks unimportant'})
        plan, report = self.compile(cues, exclude={2: 'manually reviewed'}, allow_numeric_exclusion=True)
        self.assertEqual(len(report['excluded_cues']), 1)
        self.assertEqual(len(plan['captions']), 2)

    def test_all_removed_is_rejected(self):
        with self.assertRaisesRegex(RoughCutError, 'all utterances excluded'):
            self.compile(exclude={1: 'one', 2: 'two'})

    def test_invalid_timing_rejected(self):
        with self.assertRaisesRegex(RoughCutError, 'overlap'):
            self.compile([Caption('a', 0, 1000), Caption('b', 900, 500)])
        with self.assertRaisesRegex(RoughCutError, 'ascending'):
            self.compile([Caption('later', 2000, 100), Caption('earlier', 200, 100)])
        with self.assertRaisesRegex(RoughCutError, 'past source'):
            self.compile([Caption('too late', 5000, 100)])
        with self.assertRaisesRegex(RoughCutError, 'timed captions'):
            self.compile([])

    def test_bad_parameters_rejected(self):
        with self.assertRaisesRegex(RoughCutError, 'out of range'):
            self.compile(merge_gap_ms=-1)
        with self.assertRaisesRegex(RoughCutError, 'fps'):
            self.compile(fps=0)

    def test_decisions_schema_and_duplicate_rejected(self):
        self.assertEqual(read_cut_decisions({'schema': 'video-clips/cut-decisions/v1',
                                            'exclude': [{'cue': 2, 'reason': 'Repeated phrase'}]}, 3),
                         {2: 'Repeated phrase'})
        with self.assertRaisesRegex(RoughCutError, 'duplicate'):
            read_cut_decisions({'schema': 'video-clips/cut-decisions/v1',
                                'exclude': [{'cue': 1, 'reason': 'a'}, {'cue': 1, 'reason': 'b'}]}, 3)
        with self.assertRaisesRegex(RoughCutError, 'schema'):
            read_cut_decisions({'exclude': []}, 3)
        with self.assertRaisesRegex(RoughCutError, 'reason'):
            read_cut_decisions({'schema': 'video-clips/cut-decisions/v1',
                                'exclude': [{'cue': 1, 'reason': ' '}]}, 3)


@unittest.skipUnless(shutil.which('ffprobe') and shutil.which('ffmpeg'), 'FFmpeg not installed')
class RoughCutIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', 'testsrc2=s=320x240:r=10:d=3',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=3',
                        '-c:v', 'libx264', '-threads', '2', '-c:a', 'aac', '-shortest', str(self.source)],
                       check=True, capture_output=True, timeout=40)
        self.srt = self.root / 'speech.srt'
        self.srt.write_text('1\n00:00:00,300 --> 00:00:00,900\nFirst\n\n'
                            '2\n00:00:01,800 --> 00:00:02,400\nSecond\n', encoding='utf-8')

    def test_probe_real_media(self):
        meta = video_metadata(self.source)
        self.assertEqual((meta['width'], meta['height'], meta['fps']), (320, 240, 10))
        self.assertEqual(meta['duration_ms'], 3000)

    def test_cli_plan_and_review_then_render(self):
        plan = self.root / 'rough.json'
        output = self.root / 'final.mp4'
        with contextlib.redirect_stdout(io.StringIO()):
            status = main(['rough-cut', str(self.source), '--srt', str(self.srt),
                           '--merge-gap-ms', '300', '--out', str(plan)])
        self.assertEqual(status, 0)
        report = self.root / 'rough.review.json'
        self.assertTrue(report.is_file())
        actual_plan = load_plan(plan)
        self.assertEqual(len(actual_plan.videos), 2)
        self.assertEqual([x.text for x in actual_plan.captions], ['First', 'Second'])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['render', str(plan), '--out', str(output)]), 0)
        self.assertTrue(output.is_file())
        rendered = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                   '-of', 'json', str(output)], capture_output=True, text=True, check=True)
        self.assertAlmostEqual(float(json.loads(rendered.stdout)['format']['duration']),
                               actual_plan.duration_ms / 1000, delta=.2)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['rough-cut', str(self.source), '--srt', str(self.srt),
                                   '--out', str(plan)]), 2)


if __name__ == '__main__':
    unittest.main()
