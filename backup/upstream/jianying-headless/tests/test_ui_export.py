"""Offline checks for the UI export acceptance path.

The editor does the rendering, so these tests cover the part that is ours: which
containers this path accepts, that it inherits the exact frame-count policy
instead of relaxing it, which runtimes it is registered for, and the draft-change
report. No app, codec, media, draft or network is needed.

Passing here establishes nothing about a real export; the 2026-10-20 acceptance
is recorded in docs/VERIFICATION.md.
"""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'engine'))
import runtime_profiles as profiles  # noqa: E402
import ui_export  # noqa: E402

SETTINGS = {'width': 640, 'height': 360, 'fps': 30, 'bitrate': 4_000_000, 'timeout_seconds': 600}


def probe(frames, brand='qt  ', duration='2.000000', audio=True, **video):
    streams = [dict({'codec_type': 'video', 'codec_name': 'h264', 'width': 640, 'height': 360,
                     'r_frame_rate': '30/1', 'nb_frames': str(frames)}, **video)]
    if audio:
        streams.append({'codec_type': 'audio', 'codec_name': 'aac'})
    return {'streams': streams, 'format': {'duration': duration, 'tags': {'major_brand': brand}}}


class ContainerTests(unittest.TestCase):
    def test_the_editors_quicktime_branded_mp4_is_accepted_and_reported(self):
        media = ui_export.validate_container(probe(60), SETTINGS, 2_000_000, True)
        self.assertEqual(media['major_brand'], 'qt  ')
        self.assertEqual(media['container_writer'], 'Jianying export dialog')
        self.assertEqual((media['frames'], media['expected_frames']), (60, 60))

    def test_every_reviewed_brand_is_accepted_and_others_are_not(self):
        for brand in ui_export.CONTAINER_BRANDS:
            with self.subTest(brand=brand):
                self.assertEqual(
                    ui_export.validate_container(probe(60, brand), SETTINGS, 2_000_000, True)['major_brand'],
                    brand)
        for brand in ('avi', 'matroska', '', None, 'QT  '):
            with self.subTest(rejected=brand), self.assertRaises(ValueError):
                ui_export.validate_container(probe(60, brand), SETTINGS, 2_000_000, True)

    def test_the_headless_brand_set_is_not_widened_by_this_path(self):
        import native_export
        self.assertNotIn('qt  ', ('isom', 'mp41', 'mp42'))
        with self.assertRaises(ValueError):
            native_export.validate_probe(probe(60), SETTINGS, 2_000_000, True)

    def test_a_short_or_long_export_is_still_refused(self):
        for frames in (59, 61, 0):
            with self.subTest(frames=frames), self.assertRaises(ValueError):
                ui_export.validate_container(probe(frames), SETTINGS, 2_000_000, True)

    def test_canvas_rate_codec_and_missing_audio_stay_strict(self):
        cases = {
            'canvas': dict(width=1280),
            'rate': dict(r_frame_rate='25/1'),
            'codec': dict(codec_name='hevc'),
        }
        for name, override in cases.items():
            with self.subTest(case=name), self.assertRaises(ValueError):
                ui_export.validate_container(probe(60, **override), SETTINGS, 2_000_000, True)
        with self.assertRaises(ValueError):
            ui_export.validate_container(probe(60, audio=False), SETTINGS, 2_000_000, True)

    def test_the_input_probe_is_not_mutated_by_the_brand_substitution(self):
        info = probe(60)
        before = deepcopy(info)
        ui_export.validate_container(info, SETTINGS, 2_000_000, True)
        self.assertEqual(info, before)


class ProfileTests(unittest.TestCase):
    def test_only_the_runtime_with_actual_evidence_is_registered(self):
        self.assertEqual(profiles.UI_EXPORT_PROFILES,
                         frozenset((profiles.PROFILE_PREFIX + '11.6.0',)))

    def test_this_set_is_separate_from_the_headless_export_set(self):
        self.assertFalse(profiles.UI_EXPORT_PROFILES & profiles.EXPORT_PROFILES)
        self.assertEqual(profiles.EXPORT_PROFILES,
                         frozenset(profiles.PROFILE_PREFIX + v for v in ('11.5.0', '11.4.2')))


class DraftChangeTests(unittest.TestCase):
    def manifest(self, folder, files):
        for name, body in files.items():
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding='utf-8')

    def test_what_the_editor_touched_is_counted_and_named(self):
        import jy14_headless as j
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'draft'
            folder.mkdir()
            self.manifest(folder, {'draft_info.json': 'one', 'gone.txt': 'two'})
            document = {'draft_files_before': j.files_manifest(folder)}
            (folder / 'gone.txt').unlink()
            (folder / 'draft_info.json').write_text('changed', encoding='utf-8')
            self.manifest(folder, {'.backup/new.bak': 'three'})
            changes = ui_export.draft_changes(document, folder)
        self.assertEqual((changes['added'], changes['changed'], changes['removed']), (1, 1, 1))
        self.assertEqual(changes['changed_names'], ['draft_info.json'])
        self.assertEqual(changes['removed_names'], ['gone.txt'])
        self.assertIn('source-unchanged', changes['note'])

    def test_an_untouched_draft_reports_nothing(self):
        import jy14_headless as j
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'draft'
            folder.mkdir()
            self.manifest(folder, {'draft_info.json': 'one'})
            changes = ui_export.draft_changes({'draft_files_before': j.files_manifest(folder)}, folder)
        self.assertEqual((changes['added'], changes['changed'], changes['removed']), (0, 0, 0))


if __name__ == '__main__':
    unittest.main()
