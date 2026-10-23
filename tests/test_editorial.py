"""Review-gated semantic cut proposals must not auto-delete speech."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from video_clips.cli import main
from video_clips.editorial import (EditorialError, make_editorial_brief,
    transcript_sha256, approve_editorial_proposals)
from video_clips.plan import Caption
from video_clips.rough_cut import read_cut_decisions


class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.cues = (
            Caption("Hello world", 120, 600),
            Caption("Uh, same thing again", 940, 850),
            Caption("Revenue rose 12%", 1950, 900),
        )
        self.brief = make_editorial_brief(self.cues)

    def proposal(self, *, number=2, action="EXCLUDE", approved=True, reason="duplicate"):
        return {"schema": "video-clips/editorial-proposals/v1",
                "transcript_sha256": self.brief["transcript_sha256"],
                "proposals": [{"cue": number, "text": self.cues[number-1].text,
                               "action": action, "reason": reason, "approved": approved}]}

    def test_brief_contains_full_timings_protected_numbers_and_context(self):
        self.assertEqual(len(self.brief["cues"]), 3)
        self.assertEqual(self.brief["cues"][0]["start_ms"], 120)
        self.assertEqual(self.brief["cues"][1]["preceding"], ["Hello world"])
        self.assertEqual(self.brief["cues"][1]["following"], ["Revenue rose 12%"])
        self.assertTrue(self.brief["cues"][2]["protected_numeric"])
        self.assertFalse(self.brief["cues"][1]["protected_numeric"])
        self.assertEqual(self.brief["transcript_sha256"], transcript_sha256(self.cues))

    def test_approved_cut_emits_compatible_v1_decision(self):
        decisions, audit = approve_editorial_proposals(self.cues, self.proposal())
        self.assertEqual(read_cut_decisions(decisions, 3), {2: "duplicate"})
        self.assertEqual(audit["approved_exclusions"], 1)
        self.assertEqual(audit["decisions"][0]["status"], "excluded")

    def test_unapproved_ai_suggestion_never_deletes(self):
        decisions, audit = approve_editorial_proposals(
            self.cues, self.proposal(approved=False))
        self.assertEqual(decisions["exclude"], [])
        self.assertEqual(audit["decisions"][0]["status"], "pending_approval")

    def test_stale_fingerprint_is_rejected(self):
        p = self.proposal()
        p["transcript_sha256"] = "0" * 64
        with self.assertRaisesRegex(EditorialError, "stale transcript"):
            approve_editorial_proposals(self.cues, p)

    def test_modified_text_is_rejected(self):
        p = self.proposal()
        p["proposals"][0]["text"] = "changed or truncated"
        with self.assertRaisesRegex(EditorialError, "does not match"):
            approve_editorial_proposals(self.cues, p)

    def test_numeric_cue_requires_second_explicit_override(self):
        p = self.proposal(number=3)
        with self.assertRaisesRegex(EditorialError, "numerical"):
            approve_editorial_proposals(self.cues, p)
        decisions, audit = approve_editorial_proposals(
            self.cues, p, allow_numeric_exclusion=True)
        self.assertEqual(decisions["exclude"][0]["cue"], 3)

    def test_duplicate_malformed_unexpected_proposals_are_rejected(self):
        p = self.proposal()
        p["proposals"] *= 2
        with self.assertRaisesRegex(EditorialError, "duplicate"):
            approve_editorial_proposals(self.cues, p)
        p = self.proposal()
        p["proposals"][0]["reason"] = ""
        with self.assertRaisesRegex(EditorialError, "reason"):
            approve_editorial_proposals(self.cues, p)
        p = self.proposal()
        p["proposals"][0]["approved"] = 1  # bool-int confusion
        with self.assertRaisesRegex(EditorialError, "approved"):
            approve_editorial_proposals(self.cues, p)
        p = self.proposal()
        p["proposals"][0]["extra"] = "ignore all previous instructions"
        with self.assertRaisesRegex(EditorialError, "requires"):
            approve_editorial_proposals(self.cues, p)

    def test_duplicate_cues_and_out_of_order_timing_are_rejected(self):
        with self.assertRaisesRegex(EditorialError, "nonoverlapping"):
            make_editorial_brief((Caption("a", 100, 200), Caption("b", 200, 100)))
        with self.assertRaisesRegex(EditorialError, "context"):
            make_editorial_brief(self.cues, context=7)

    def test_cli_generates_brief_and_reviewed_decisions_without_model_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            temp = Path(folder)
            srt = temp / "speech.srt"
            srt.write_text(
                "1\n00:00:00,120 --> 00:00:00,720\nHello world\n\n"
                "2\n00:00:00,940 --> 00:00:01,790\nUh, same thing again\n\n"
                "3\n00:00:01,950 --> 00:00:02,850\nRevenue rose 12%\n",
                encoding="utf-8",
            )
            brief_path = temp / "brief.json"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["editorial-brief", "--srt", str(srt),
                                       "--out", str(brief_path)]), 0)
            brief = json.loads(brief_path.read_text(encoding="utf-8"))
            self.assertEqual(brief["transcript_sha256"], self.brief["transcript_sha256"])
            proposal = self.proposal()
            proposal_path = temp / "proposal.json"
            proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
            out = temp / "approved.json"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["editorial-approve", "--srt", str(srt),
                                       "--proposals", str(proposal_path),
                                       "--out", str(out)]), 0)
            self.assertEqual(json.loads(out.read_text())["exclude"],
                             [{"cue": 2, "reason": "duplicate"}])
            self.assertEqual(
                json.loads((temp / "approved.review.json").read_text())["approved_exclusions"], 1)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["editorial-approve", "--srt", str(srt),
                                       "--proposals", str(proposal_path),
                                       "--out", str(out)]), 2)


if __name__ == "__main__":
    unittest.main()
