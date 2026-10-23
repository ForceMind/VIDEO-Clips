import copy
import unittest
from video_clips.agent import AgentOptions, AGENT_SCHEMA, compile_agent_decisions, agent_request, strict_json
from video_clips.editorial import EditorialError, transcript_sha256
from video_clips.plan import Caption


def response_for(cues):
    return {'schema': AGENT_SCHEMA, 'transcript_sha256': transcript_sha256(cues),
            'decisions': [{'cue': i, 'text': c.text.strip(), 'action': 'KEEP',
                           'reason': 'Preserves the central argument', 'category': 'important',
                           'confidence': .99, 'duplicate_of': None} for i, c in enumerate(cues, 1)]}


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.cues = [Caption('Core idea', 100, 600), Caption('Um', 900, 500),
                     Caption('Revenue is 12%', 1600, 600), Caption('VIDEO-Clips works locally', 2400, 700)]
        self.payload = response_for(self.cues)
        for r in self.payload['decisions'][1:]:
            r.update(action='EXCLUDE', category='filler', reason='Standalone filler')
        self.options = AgentOptions('Tighten the explanation', protected_terms=('VIDEO-Clips',), apply_cuts=True)

    def test_policy_keeps_numbers_and_names_but_applies_filler(self):
        decisions, proposals, report = compile_agent_decisions(self.cues, self.payload, self.options)
        self.assertEqual([d['cue'] for d in decisions['exclude']], [2])
        self.assertEqual(len(proposals['proposals']), 4)
        self.assertIn('numeric content protected', report['policy_decisions'][2]['blocked_by'])
        self.assertIn('protected term', report['policy_decisions'][3]['blocked_by'])

    def test_default_is_review_only(self):
        decisions, _, report = compile_agent_decisions(self.cues, self.payload, AgentOptions('Tighten'))
        self.assertEqual(decisions['exclude'], [])
        self.assertFalse(report['auto_apply_requested'])

    def test_strategy_threshold_category_and_uncertainty(self):
        p = response_for(self.cues)
        p['decisions'][1].update(action='EXCLUDE', category='low_value')
        for strategy in ['conservative', 'standard']:
            d, _, _ = compile_agent_decisions(self.cues, p, AgentOptions('Edit', strategy, apply_cuts=True))
            self.assertFalse(d['exclude'])
        for strategy in ['aggressive', 'highlights']:
            d, _, _ = compile_agent_decisions(self.cues, p, AgentOptions('Edit', strategy, apply_cuts=True))
            self.assertEqual(d['exclude'][0]['cue'], 2)
        p['decisions'][1].update(category='filler', confidence=.91)
        d, _, _ = compile_agent_decisions(self.cues, p, AgentOptions('Edit', 'conservative', apply_cuts=True))
        self.assertFalse(d['exclude'])
        p['decisions'][1].update(category='context', confidence=1)
        d, _, _ = compile_agent_decisions(self.cues, p, AgentOptions('Edit', 'highlights', apply_cuts=True))
        self.assertFalse(d['exclude'])

    def test_coverage_fingerprint_text_times_and_approvals_rejected(self):
        cases = []
        p = copy.deepcopy(self.payload); p['decisions'].pop(); cases.append(p)
        p = copy.deepcopy(self.payload); p['transcript_sha256'] = 'bad'; cases.append(p)
        p = copy.deepcopy(self.payload); p['decisions'][1]['text'] = 'invented'; cases.append(p)
        p = copy.deepcopy(self.payload); p['decisions'][1]['start_ms'] = 23; cases.append(p)
        p = copy.deepcopy(self.payload); p['decisions'][1]['approved'] = True; cases.append(p)
        p = copy.deepcopy(self.payload); p['decisions'][1]['cue'] = True; cases.append(p)
        p = copy.deepcopy(self.payload); p['decisions'][1]['confidence'] = float('nan'); cases.append(p)
        p = copy.deepcopy(self.payload); p['decisions'][1]['category'] = []; cases.append(p)
        for p in cases:
            with self.subTest(payload=p), self.assertRaises(EditorialError):
                compile_agent_decisions(self.cues, p, self.options)

    def test_duplicate_reference_must_be_kept_and_exact_when_conservative(self):
        p = response_for(self.cues)
        p['decisions'][1].update(action='EXCLUDE', category='duplicate', duplicate_of=1)
        d, _, report = compile_agent_decisions(self.cues, p, AgentOptions('Edit', 'conservative', apply_cuts=True))
        self.assertFalse(d['exclude'])
        self.assertIn('conservative duplicate is not exact text', report['policy_decisions'][1]['blocked_by'])
        p['decisions'][0]['action'] = 'EXCLUDE'
        with self.assertRaisesRegex(EditorialError, 'retained'):
            compile_agent_decisions(self.cues, p, self.options)
        p['decisions'][0] = None
        with self.assertRaises(EditorialError):
            compile_agent_decisions(self.cues, p, self.options)

    def test_exact_duplicate_applies_and_all_removed_rejected(self):
        cues = [Caption('Same', 0, 500), Caption('Same', 900, 500)]
        p = response_for(cues)
        p['decisions'][1].update(action='EXCLUDE', category='duplicate', duplicate_of=1)
        d, _, _ = compile_agent_decisions(cues, p, AgentOptions('Edit', 'conservative', apply_cuts=True))
        self.assertEqual(d['exclude'][0]['cue'], 2)
        for r in p['decisions']:
            r.update(action='EXCLUDE', category='filler', duplicate_of=None)
        with self.assertRaisesRegex(EditorialError, 'all content'):
            compile_agent_decisions(cues, p, AgentOptions('Edit', apply_cuts=True))

    def test_strict_json_and_options(self):
        for raw in ['{"x":1,"x":2}', '{"x":NaN}', '```json\n{}\n```']:
            with self.assertRaises(EditorialError): strict_json(raw)
        for options in [AgentOptions(''), AgentOptions('Edit', 'unknown'), AgentOptions('Edit', target_ms=True),
                        AgentOptions('Edit', protected_terms=('',))]:
            with self.assertRaises(EditorialError): agent_request(self.cues, options)
