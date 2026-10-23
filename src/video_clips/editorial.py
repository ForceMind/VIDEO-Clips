"""Offline, transcript-bound editorial brief and approval compiler.

An AI may propose cuts, but only a reviewer-approved, transcript-matched
proposal is allowed into the executable cut decisions. No model/API calls.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from .plan import Caption

BRIEF_SCHEMA = "video-clips/editorial-brief/v1"
PROPOSALS_SCHEMA = "video-clips/editorial-proposals/v1"
DECISIONS_SCHEMA = "video-clips/cut-decisions/v1"
NUMBER_PATTERN = re.compile(r"\d|[零一二三四五六七八九十百千万亿两]|[$¥￥%％]")


class EditorialError(ValueError):
    """Reject stale, ambiguous or unapproved editorial decisions."""


def _cues(captions: Sequence[Caption]) -> list[dict]:
    if not captions or len(captions) > 1000:
        raise EditorialError("a transcript must contain 1..1000 timed captions")
    result = []
    previous_end = -1
    for index, cue in enumerate(captions, 1):
        if not isinstance(cue, Caption):
            raise EditorialError("all cues must be timed Caption records")
        if (not isinstance(cue.text, str) or type(cue.start_ms) is not int or type(cue.duration_ms) is not int
                or not cue.text.strip() or len(cue.text) > 500 or cue.start_ms < 0 or cue.duration_ms <= 0):
            raise EditorialError("caption text or times are invalid")
        if cue.start_ms < previous_end or cue.end_ms > 21_600_000:
            raise EditorialError("transcript cues must be chronological and nonoverlapping")
        result.append({"cue": index, "start_ms": cue.start_ms,
                       "end_ms": cue.end_ms, "text": cue.text.strip()})
        previous_end = cue.end_ms
    return result


def transcript_sha256(captions: Sequence[Caption]) -> str:
    payload = {"schema": "video-clips/transcript/v1", "cues": _cues(captions)}
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def make_editorial_brief(captions: Sequence[Caption], *, context: int = 1) -> dict:
    if type(context) is not int or not 0 <= context <= 3:
        raise EditorialError("context must be an integer between 0 and 3")
    cues = _cues(captions)
    enriched = []
    for i, cue in enumerate(cues):
        enriched.append({
            **cue,
            "protected_numeric": bool(NUMBER_PATTERN.search(cue["text"])),
            "preceding": [c["text"] for c in cues[max(0, i-context):i]],
            "following": [c["text"] for c in cues[i+1:i+context+1]],
        })
    return {
        "schema": BRIEF_SCHEMA,
        "transcript_sha256": transcript_sha256(captions),
        "total_cues": len(cues),
        "instructions": [
            "Propose semantic KEEP or EXCLUDE for specific cue numbers only.",
            "Do not invent time boundaries or rewrite cue texts. Echo cue text verbatim.",
            "Flag duplicates or verbal fillers with a specific reason, not subjective guesses.",
            "Preserve numbers, prices, names, crucial meaning, and uncertain content.",
            "Proposals are NON-DESTRUCTIVE; a human must set approved=true before EXCLUDE applies.",
        ],
        "proposal_schema": PROPOSALS_SCHEMA,
        "cues": enriched,
    }


def approve_editorial_proposals(
    captions: Sequence[Caption], payload: object, *, allow_numeric_exclusion: bool = False
) -> tuple[dict, dict]:
    cues = _cues(captions)
    digest = transcript_sha256(captions)
    if not isinstance(payload, dict) or set(payload) != {"schema", "transcript_sha256", "proposals"}:
        raise EditorialError("proposal requires schema, transcript_sha256 and proposals only")
    if payload["schema"] != PROPOSALS_SCHEMA:
        raise EditorialError("unsupported editorial proposal schema")
    if payload["transcript_sha256"] != digest:
        raise EditorialError("stale transcript fingerprint; proposals cannot be reused")
    proposals = payload["proposals"]
    if not isinstance(proposals, list) or len(proposals) > len(cues):
        raise EditorialError("proposals must be a list no longer than the cue count")
    excluded = []
    reviewed = []
    seen = set()
    for raw in proposals:
        if not isinstance(raw, dict) or set(raw) != {"cue", "text", "action", "reason", "approved"}:
            raise EditorialError("proposal requires cue, text, action, reason and approved only")
        number = raw["cue"]
        if type(number) is not int or number < 1 or number > len(cues) or number in seen:
            raise EditorialError("duplicate or out-of-range proposal cue")
        seen.add(number)
        original = cues[number-1]["text"]
        if raw["text"] != original:
            raise EditorialError(f"cue {number} text does not match source transcript")
        action, approved = raw["action"], raw["approved"]
        if action not in ("KEEP", "EXCLUDE") or type(approved) is not bool:
            raise EditorialError("invalid action or approved flag")
        reason = raw["reason"]
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 200:
            raise EditorialError("proposal reason must contain 1..200 characters")
        status = "kept"
        if action == "EXCLUDE" and approved:
            if NUMBER_PATTERN.search(original) and not allow_numeric_exclusion:
                raise EditorialError(f"cue {number} contains numerical content; explicit override required")
            excluded.append({"cue": number, "reason": reason.strip()})
            status = "excluded"
        elif action == "EXCLUDE":
            status = "pending_approval"
        reviewed.append({"cue": number, "action": action, "approved": approved,
                         "status": status, "reason": reason.strip()})
    decisions = {"schema": DECISIONS_SCHEMA, "exclude": sorted(excluded, key=lambda x: x["cue"])}
    audit = {"schema": "video-clips/editorial-review/v1", "transcript_sha256": digest,
             "total_cues": len(cues), "proposed": len(proposals),
             "approved_exclusions": len(excluded), "decisions": reviewed,
             "warnings": [
                 "Only approved EXCLUDE proposals are actionable.",
                 "Transcription can miss valuable video/audio; review final rough cut before publishing.",
                 "Numeric exclusions also require --allow-numeric-exclusion when running rough-cut.",
             ]}
    return decisions, audit
