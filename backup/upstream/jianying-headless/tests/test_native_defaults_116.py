"""Offline 11.6.0 saved-readback regressions, through the real verify_live entry.

Each rule here mirrors a 2026-10-20 native UI save on the maintenance Mac:
omitted `fps`, omitted unit segment `speed` and `volume`, regenerated empty photo
companions including one the 185 source never had, and the custom-curve average
recalculated against the frame-floored target duration. The fixtures themselves
are synthetic and need no app, codec, account, media, user draft or network.
Passing offline does not establish native UI acceptance on any other machine.
"""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'engine'))
import native_edit as edit  # noqa: E402

from test_native_defaults_115 import saved_copy_fixture, timeline  # noqa: E402

PROFILE = 'jy14-headless-macos-11.6.0'
PROFILE_115 = 'jy14-headless-macos-11.5.0'


def saved_116():
    """The 11.5 synthetic shape restamped as a draft this runtime saved."""
    document = timeline()
    document['new_version'] = '189.0.0'
    document['last_modified_platform'] = {'app_version': '11.6.0', 'os': 'mac'}
    for track in document['tracks']:
        track['segments'][0]['volume'] = 1
    return document


def owners(document, kind):
    index = 0 if kind == 'video' else 1
    return document['materials']['speeds'][index], document['tracks'][index]['segments'][0]


class SavedDefaultTests(unittest.TestCase):
    """fps, segment speed and segment volume omissions observed on 11.6.0."""

    def omitted(self, *locations):
        expected = saved_116()
        actual = deepcopy(expected)
        for location in locations:
            if location == 'fps':
                del actual['fps']
            else:
                kind, field = location.split('.')
                del owners(actual, kind)[1][field]
        return expected, actual

    def test_observed_omissions_compare_equal_in_both_directions(self):
        for locations in (('fps',), ('video.speed',), ('audio.speed',),
                          ('video.volume',), ('audio.volume',),
                          ('fps', 'video.speed', 'audio.speed', 'video.volume', 'audio.volume')):
            for reverse in (False, True):
                expected, actual = self.omitted(*locations)
                if reverse:
                    expected, actual = actual, expected
                with self.subTest(locations=locations, reverse=reverse):
                    with saved_copy_fixture(expected, actual, PROFILE) as (out, _, __):
                        self.assertEqual(edit.verify_live(out)['status'], 'verified')

    def test_nondefault_values_are_never_hidden_by_an_omission(self):
        for kind in ('video', 'audio'):
            for field, value in (('speed', 1.5), ('volume', 0.3)):
                for reverse in (False, True):
                    expected = saved_116()
                    actual = deepcopy(expected)
                    owners(expected, kind)[1][field] = value
                    del owners(actual, kind)[1][field]
                    if reverse:
                        expected, actual = actual, expected
                    with self.subTest(kind=kind, field=field, reverse=reverse):
                        with saved_copy_fixture(expected, actual, PROFILE) as (out, _, __):
                            with self.assertRaises(ValueError):
                                edit.verify_live(out)

    def test_muted_and_explicit_volumes_stay_comparable_and_typed(self):
        for value in (0, 0.0, 2, 3.5):
            expected = saved_116()
            for kind in ('video', 'audio'):
                owners(expected, kind)[1]['volume'] = value
            actual = deepcopy(expected)
            with self.subTest(value=value):
                with saved_copy_fixture(expected, actual, PROFILE) as (out, _, __):
                    self.assertEqual(edit.verify_live(out)['status'], 'verified')
        for value in (True, None, '1', -1):
            expected = saved_116()
            actual = deepcopy(expected)
            owners(actual, 'video')[1]['volume'] = value
            with self.subTest(invalid=repr(value)):
                with saved_copy_fixture(expected, actual, PROFILE) as (out, _, __):
                    with self.assertRaises(ValueError):
                        edit.verify_live(out)
        # A non-finite volume cannot reach a saved draft through the strict JSON
        # writer, so this one is checked against the comparison entry directly.
        expected = saved_116()
        actual = deepcopy(expected)
        owners(actual, 'video')[1]['volume'] = float('nan')
        with self.assertRaises(ValueError):
            edit.compare_saved_timeline(expected, actual, PROFILE)

    def test_115_and_legacy_profiles_do_not_gain_the_volume_exception(self):
        for profile, schema, app in ((PROFILE_115, '187.0.0', '11.5.0'),
                                     ('jy14-headless-macos-11.4.2', '185.0.0', '11.4.2')):
            expected = saved_116()
            expected['new_version'] = schema
            expected['last_modified_platform'] = {'app_version': app, 'os': 'mac'}
            actual = deepcopy(expected)
            del owners(actual, 'video')[1]['volume']
            with self.subTest(profile=profile):
                with saved_copy_fixture(expected, actual, profile) as (out, _, __):
                    with self.assertRaises(ValueError):
                        edit.verify_live(out)


def photo_pair(*, add_loudness=True, rename_vocal=True):
    """A photo segment whose empty companions this runtime rewrites on save."""
    expected = {'id': 'photo-timeline', 'version': 360000, 'new_version': '189.0.0',
                'fps': 30.0, 'duration': 3000000, 'canvas_config': {'width': 640, 'height': 360},
                'last_modified_platform': {'app_version': '11.6.0', 'os': 'mac'},
                'materials': {'videos': [{'id': 'picture', 'type': 'photo', 'has_audio': False}],
                              'speeds': [{'id': 'photo-speed', 'type': 'speed', 'speed': 1}],
                              'vocal_separations': [{'id': 'old-vocal', 'type': 'vocal_separation'}]},
                'tracks': [{'id': 'photo-track', 'type': 'video', 'segments': [
                    {'id': 'photo-segment', 'material_id': 'picture', 'speed': 1, 'volume': 1,
                     'extra_material_refs': ['photo-speed', 'old-vocal'],
                     'source_timerange': {'start': 0, 'duration': 3000000},
                     'target_timerange': {'start': 0, 'duration': 3000000}}]}]}
    actual = deepcopy(expected)
    refs = actual['tracks'][0]['segments'][0]['extra_material_refs']
    if rename_vocal:
        actual['materials']['vocal_separations'][0]['id'] = 'new-vocal'
        refs[refs.index('old-vocal')] = 'new-vocal'
    if add_loudness:
        actual['materials']['loudnesses'] = [{'id': 'new-loudness'}]
        refs.insert(len(refs) - 1, 'new-loudness')
    return expected, actual


class PhotoCompanionTests(unittest.TestCase):
    def test_regenerated_and_added_companions_are_reported_without_rewriting_evidence(self):
        expected, actual = photo_pair()
        untouched = deepcopy(actual)
        compared, rows = edit.normalize_saved_companions(expected, actual, PROFILE)
        self.assertEqual(actual, untouched)
        identities = [row for row in rows if 'expected_id' in row]
        additions = [row for row in rows if 'expected_id' not in row]
        self.assertEqual([(row['bucket'], row['expected_id'], row['native_id']) for row in identities],
                         [('vocal_separations', 'old-vocal', 'new-vocal')])
        self.assertEqual([(row['bucket'], row['added_native_id']) for row in additions],
                         [('loudnesses', 'new-loudness')])
        edit.preserved(expected, compared)

    def test_an_existing_loudness_is_repaired_by_identity_not_treated_as_new(self):
        # A 189 source already carries both companions; the cold-reopen save
        # renames both. Neither may be dropped as an addition.
        expected, actual = photo_pair(add_loudness=False)
        refs = expected['tracks'][0]['segments'][0]['extra_material_refs']
        expected['materials']['loudnesses'] = [{'id': 'old-loudness'}]
        refs.insert(len(refs) - 1, 'old-loudness')
        actual['materials']['loudnesses'] = [{'id': 'new-loudness'}]
        saved_refs = actual['tracks'][0]['segments'][0]['extra_material_refs']
        saved_refs.insert(len(saved_refs) - 1, 'new-loudness')
        compared, rows = edit.normalize_saved_companions(expected, actual, PROFILE)
        self.assertEqual(sorted(row['bucket'] for row in rows),
                         ['loudnesses', 'vocal_separations'])
        self.assertTrue(all('expected_id' in row for row in rows))
        edit.preserved(expected, compared)

    def test_each_observed_change_also_passes_on_its_own(self):
        for add_loudness, rename_vocal in ((True, False), (False, True)):
            expected, actual = photo_pair(add_loudness=add_loudness, rename_vocal=rename_vocal)
            with self.subTest(add_loudness=add_loudness, rename_vocal=rename_vocal):
                compared, rows = edit.normalize_saved_companions(expected, actual, PROFILE)
                self.assertEqual(len(rows), 1)
                edit.preserved(expected, compared)

    def test_other_runtimes_stamps_materials_and_nondefault_nodes_stay_strict(self):
        for case in ('runtime', 'schema', 'app', 'not_photo', 'has_audio',
                     'valued_addition', 'shared_addition', 'other_bucket', 'extra_ref'):
            expected, actual = photo_pair()
            runtime = PROFILE
            if case == 'runtime':
                runtime = PROFILE_115
            elif case == 'schema':
                actual['new_version'] = expected['new_version'] = '187.0.0'
            elif case == 'app':
                actual['last_modified_platform']['app_version'] = '11.5.0'
            elif case == 'not_photo':
                expected['materials']['videos'][0]['type'] = 'video'
                actual['materials']['videos'][0]['type'] = 'video'
            elif case == 'has_audio':
                expected['materials']['videos'][0]['has_audio'] = True
                actual['materials']['videos'][0]['has_audio'] = True
            elif case == 'valued_addition':
                actual['materials']['loudnesses'][0]['gain'] = 0.5
            elif case == 'shared_addition':
                actual['tracks'][0]['segments'].append(
                    {'id': 'other-segment', 'material_id': 'picture',
                     'extra_material_refs': ['new-loudness'],
                     'source_timerange': {'start': 0, 'duration': 1},
                     'target_timerange': {'start': 3000000, 'duration': 1}})
            elif case == 'other_bucket':
                actual['materials']['vocal_separations'].append({'id': 'extra', 'type': 'vocal_separation'})
                refs = actual['tracks'][0]['segments'][0]['extra_material_refs']
                refs.insert(0, 'extra')
            else:
                actual['materials']['canvases'] = [{'id': 'extra-canvas'}]
                actual['tracks'][0]['segments'][0]['extra_material_refs'].append('extra-canvas')
            with self.subTest(case=case):
                compared, _ = edit.normalize_saved_companions(expected, actual, runtime)
                with self.assertRaises(ValueError):
                    edit.preserved(expected, compared)


def curve_pair(target_us, native_speed):
    """The 2026-10-20 nonflat custom curve, with its own saved average."""
    stored = 1.5616438314318657
    expected = {'id': 'curve-timeline', 'version': 360000, 'new_version': '189.0.0',
                'fps': 30.0, 'duration': target_us, 'canvas_config': {'width': 640, 'height': 360},
                'last_modified_platform': {'app_version': '11.6.0', 'os': 'mac'},
                'materials': {
                    'videos': [{'id': 'video', 'type': 'video'}],
                    'speeds': [{'id': 'curve-speed', 'type': 'speed', 'mode': 1, 'speed': stored,
                                'curve_speed': {'id': '6768730851543880206', 'name': '自定义',
                                                'speed_points': [
                                                    {'x': 0.0, 'y': 1.0}, {'x': 0.25, 'y': 1.0},
                                                    {'x': 0.5017006802721088, 'y': 4.2},
                                                    {'x': 0.75, 'y': 1.0}, {'x': 1.0, 'y': 1.0}]}}]},
                'tracks': [{'id': 'curve-track', 'type': 'video', 'segments': [{
                    'id': 'curve-segment', 'material_id': 'video', 'volume': 1,
                    'extra_material_refs': ['curve-speed'], 'speed': stored,
                    'source_timerange': {'start': 0, 'duration': 2000000},
                    'target_timerange': {'start': 0, 'duration': target_us}}]}]}
    actual = deepcopy(expected)
    actual['materials']['speeds'][0]['speed'] = native_speed
    actual['tracks'][0]['segments'][0]['speed'] = native_speed
    return expected, actual


FLOORED = 2000000 / 1266666


class CurveAverageTests(unittest.TestCase):
    """11.6.0 divided by the frame-floored target, not the stored one."""

    def test_both_observed_targets_accept_the_frame_floored_average(self):
        for target_us in (1266666, 1266667):
            expected, actual = curve_pair(target_us, FLOORED)
            with self.subTest(target_us=target_us):
                with saved_copy_fixture(expected, actual, PROFILE) as (out, _, __):
                    result = edit.verify_live(out)
                    self.assertEqual(result['status'], 'verified')
                    changes = result['native_curve_speed_recomputations']
                    self.assertEqual(len(changes), 1)
                    self.assertEqual(changes[0]['native_speed'], FLOORED)
                    self.assertEqual(changes[0]['target_duration_us'], target_us)
                    self.assertEqual(changes[0]['reference_duration_us'], 1266666)
                    self.assertGreater(changes[0]['frame_rounding_us'], 0)

    def test_the_115_divisor_is_not_accepted_on_this_runtime(self):
        # 2000000/1266667 is what 11.5 would have written; 11.6 never did.
        expected, actual = curve_pair(1266667, 2000000 / 1266667)
        with saved_copy_fixture(expected, actual, PROFILE) as (out, _, __):
            with self.assertRaises(ValueError):
                edit.verify_live(out)

    def test_other_runtimes_stamps_shapes_and_timings_stay_strict(self):
        for case in ('runtime', 'schema', 'app', 'points', 'ranges', 'identity', 'split_owners'):
            expected, actual = curve_pair(1266666, FLOORED)
            profile = PROFILE
            if case == 'runtime':
                profile = PROFILE_115
            elif case == 'schema':
                expected['new_version'] = actual['new_version'] = '187.0.0'
            elif case == 'app':
                actual['last_modified_platform']['app_version'] = '11.5.0'
            elif case == 'points':
                actual['materials']['speeds'][0]['curve_speed']['speed_points'][2]['y'] = 3.0
            elif case == 'ranges':
                actual['tracks'][0]['segments'][0]['target_timerange']['duration'] = 1266000
            elif case == 'identity':
                actual['materials']['speeds'][0]['curve_speed']['id'] = '1234567890123456789'
                expected['materials']['speeds'][0]['curve_speed']['id'] = '1234567890123456789'
            else:
                actual['tracks'][0]['segments'][0]['speed'] = expected['tracks'][0]['segments'][0]['speed']
            with self.subTest(case=case):
                with saved_copy_fixture(expected, actual, profile) as (out, _, __):
                    with self.assertRaises(ValueError):
                        edit.verify_live(out)


if __name__ == '__main__':
    unittest.main()
