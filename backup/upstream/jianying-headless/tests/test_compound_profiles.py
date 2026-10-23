"""Which runtimes may inspect, build and read back compound structures.

This gate is about structure only. Home registration is refused on every
runtime, and delivering a frozen snapshot still needs an export path. These
tests pin both of those so widening the structural set cannot quietly widen
either one. No app, codec, media, draft or network is needed.

The 2026-10-20 acceptance behind the 11.6.0 entry is in docs/VERIFICATION.md.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'engine'))
import native_compound as compound  # noqa: E402
import runtime_profiles as profiles  # noqa: E402

PREFIX = profiles.PROFILE_PREFIX


class SupportedProfileTests(unittest.TestCase):
    def test_exactly_the_runtimes_with_compound_evidence(self):
        self.assertEqual(compound.SUPPORTED_PROFILES,
                         frozenset(PREFIX + v for v in ('11.4.2', '11.5.0', '11.6.0')))

    def test_runtimes_without_compound_evidence_stay_out(self):
        for version in ('11.4.0', '11.5.1', '11.7.0', ''):
            with self.subTest(version=version):
                self.assertNotIn(PREFIX + version, compound.SUPPORTED_PROFILES)

    def test_every_compound_runtime_is_a_known_edit_runtime(self):
        self.assertTrue(compound.SUPPORTED_PROFILES <= profiles.EDIT_PROFILES)


class StillRefusedTests(unittest.TestCase):
    def timeline(self):
        child = {'id': 'child', 'duration': 1000, 'tracks': []}
        return {'id': 'root', 'duration': 1000,
                'materials': {'drafts': [{'id': 'combination', 'type': 'combination',
                                          'combination_id': 'combo', 'draft': child}]},
                'tracks': []}

    def test_home_registration_is_refused_for_every_runtime(self):
        # require_publishable takes no profile on purpose: no runtime may register
        # a compound draft, including the ones allowed to build one offline.
        with self.assertRaises(ValueError) as caught:
            compound.require_publishable(self.timeline())
        self.assertIn('Compound live registration is blocked', str(caught.exception))

    def test_a_plain_timeline_is_still_publishable(self):
        compound.require_publishable({'id': 'root', 'duration': 1000, 'materials': {}, 'tracks': []})

    def test_adding_compound_runtimes_did_not_add_an_export_runtime(self):
        # 11.6.0 can build compound structures but has no headless export ABI,
        # so the frozen-snapshot delivery stays unavailable there.
        self.assertNotIn(PREFIX + '11.6.0', profiles.EXPORT_PROFILES)
        self.assertEqual(profiles.EXPORT_PROFILES,
                         frozenset(PREFIX + v for v in ('11.5.0', '11.4.2')))


if __name__ == '__main__':
    unittest.main()
