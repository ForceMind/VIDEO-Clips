# Agent editorial handoff and explicit approval

VIDEO-Clips now supports an **offline** AI-editorial handoff without sending source
media to a model or trusting a model's guessed timestamps.

1. Give VIDEO-Clips an existing timestamped SRT or completed StepFun file-ASR result.
2. Export a transcript-bound editorial brief. The brief includes immutable cue IDs,
   precise original cue times, context, protected-number hints and a SHA-256 fingerprint.
3. Pass the JSON brief to an AI editor of your choice. The AI **proposes**, but cannot
   directly modify footage or approve its own cuts.
4. Inspect the proposals and explicitly change `approved` to `true` for each safe exclusion.
5. Compile an executable cut-decision file with a second fingerprint/text verification,
   then feed it into the existing `rough-cut` command and render the result.

```bash
video-clips editorial-brief --srt source.srt --out work/editorial-brief.json
video-clips editorial-approve --srt source.srt   --proposals work/proposals.json --out work/reviewed-decisions.json
video-clips rough-cut source.mp4 --srt source.srt   --decisions work/reviewed-decisions.json --out work/rough.plan.json
video-clips render work/rough.plan.json --out work/review.mp4
```

To use a timestamp-bearing completed StepFun **file** ASR response instead:

```bash
video-clips editorial-brief --step-file response.json --out work/editorial-brief.json
video-clips editorial-approve --step-file response.json   --proposals work/proposals.json --out work/reviewed-decisions.json
```

The one-shot StepAudio SSE *text-only* result is not sufficient for exact cut timing.

## AI proposal format

Set `transcript_sha256` to the **exact** digest from the generated brief.
Echo the selected cue's text *exactly*, including punctuation.
The AI should output suggested exclusions with `approved: false`.
The reviewer, not the AI, flips it to `true` after checking context:

```json
{
  "schema": "video-clips/editorial-proposals/v1",
  "transcript_sha256": "<digest copied from editorial-brief.json>",
  "proposals": [
    {
      "cue": 4,
      "text": "重复说了一遍",
      "action": "EXCLUDE",
      "reason": "Duplicate of the previous statement",
      "approved": false
    }
  ]
}
```

An unapproved EXCLUDE remains in the separate audit report but is not applied.
A KEEP proposal is informational and never deletes anything.

## Safety boundaries

- A mismatched transcript digest or altered cue text **fails closed**.
- Duplicate/out-of-range cue indices, unknown fields, malformed booleans and empty
  reasons are rejected.
- Numeric, monetary or percentage-containing captions are protected:
  even an approved proposal needs `--allow-numeric-exclusion` at **both** the
  editorial approval and rough-cut steps to remove that cue.
- Original footage and transcripts are never changed. Output and audit files
  must not already exist.
- Exact cue timing comes from the source transcript, not the AI. This is a
  validated **proposal/approval contract**, not an autonomous LLM provider.
- As before, untranscribed gaps can contain valuable footage/audio and must be
  manually reviewed before using any published video.

Tests: `PYTHONPATH=src python -m unittest discover -s tests -v`.
