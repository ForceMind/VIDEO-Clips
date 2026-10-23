# Saved readback rules for Jianying 11.6.0

Jianying 11.6.0 (build 13281) rewrites a few fields every time it saves a draft.
Until 2026-10-20 the edit-copy readback only recognized the 11.5.0 forms, so an
11.6.0 copy containing a photo, a unit volume, or a UI-built speed curve was
rejected. This page records what 11.6.0 was actually observed doing, and the
exact scope each rule was given. The 11.5.0 and 11.4.x rules are unchanged; see
[the 11.5 page](SAVED-DEFAULTS-115.md) for those and for the shared mechanics.

Every rule below is keyed on the **saving runtime** and its own save stamp, and
works on comparison copies only. No live draft, saved byte or expected snapshot
is rewritten, and no rule is enabled for a runtime that was not observed.

## Omitted defaults

`native_edit.NATIVE_DEFAULT_RUNTIMES` lists the runtimes that interpret absent
fields as defaults, and the extra per-segment fields each one omits:

| Runtime | fps / speed defaults | Extra |
| --- | --- | --- |
| `jy14-headless-macos-11.5.0` | yes (unchanged) | none |
| `jy14-headless-macos-11.6.0` | yes | segment `volume` |

The fps and speed locations, supported speed contexts, and the rule that a
missing speed in an unverified context is rejected on both sides are exactly the
11.5 ones. 11.6.0 additionally omitted a segment's `volume` when it equals 1,
observed on a main-track video segment, a photo segment and an audio segment in
the same save. Filling is two-way, so an omitted volume versus `0.3` still
fails. A present volume must be a finite number `>= 0`; zero is a real muted
value and is preserved, while booleans, strings, negatives and non-finite values
are rejected. Volume omission is **not** enabled for 11.5.0 or 11.4.x, which
were not retested.

## Photo audio companions

A `has_audio: false` photo segment carries empty `loudnesses` and
`vocal_separations` companion nodes. On 11.6.0 every save gives them fresh IDs,
and a `185.0.0` source that carried no loudness companion gains one, taking the
segment's reference list from six entries to seven.

`normalize_saved_companions` now admits the 11.6.0 root timeline when the saved
document is `189.0.0` stamped `11.6.0`. Both source schemas actually observed
(`185.0.0` migrating to `189.0.0`, and a `189.0.0` re-save after a cold reopen)
pass; a `187.0.0` photo source was not sampled, because producing one needs an
11.5.0 install this machine no longer has.

`native_compound.normalize_companion_ids` gained an `added_buckets` argument,
set to `{'loudnesses'}` only for that 11.6.0 case. An added reference qualifies
only when its node is absent from the expected index, belongs to an allowed
bucket, is entirely default-valued, and is referenced exactly once in the saved
document; after removing the additions the remaining reference list must line up
one-for-one with the expected one. The comparison copy drops just those
references, so every other reference still compares exactly. Compound sidecars
and the 11.5.0 path pass no `added_buckets` and are unaffected.

## Custom-curve average recomputation

The first save of a copy recalculates the linked segment/material average of a
UI-built nonflat custom curve. 11.5.0 divided the source duration by the stored
target duration. 11.6.0 divides by that duration **floored onto the frame grid**:

```
frames    = round(target_us / (1_000_000 / fps))
reference = frames * 1_000_000 // fps
```

Measured on 2026-10-20 with two 38-frame segments from one source. Their stored
target durations were 1,266,666 and 1,266,667 microseconds, yet both saved
averages became `2000000 / 1266666`. Dividing by the stored target
would have produced a different number for the second segment and failed it, so
the divisor is recorded per runtime in `CURVE_AVERAGE_RUNTIMES` rather than
shared. A third segment in the same save kept its stored average; only changes
that actually occur are normalized, and no attempt is made to predict when the
engine chooses to recompute.

Every other condition from the 11.5 rule still applies: 30 fps, noncompound, a
uniquely referenced mode-1 material with the observed custom-curve identity and
ordered finite nonflat points, identical curve content and references, identical
source/target ranges apart from an omitted integer zero start, both averages
present, positive and nonunit on each side, the target frame-aligned within one
microsecond, and the previously implied duration exceeding the target by less
than one frame.

## Regression

```sh
python3 -m unittest discover -s tests -p test_native_defaults_116.py -v
```

Ten offline cases drive the real `verify_live` entry with synthetic documents:
both directions of each omission, nondefault values that must not be hidden,
muted and invalid volumes, 11.5.0/11.4.2 controls that must still reject a
volume omission, the regenerated and added companions together and separately,
non-default or shared companions that must stay strict, both observed curve
targets, and the 11.5.0 divisor being refused on this runtime. Offline passes do
not establish a native UI result; the 2026-10-20 acceptance is recorded in
[VERIFICATION.md](VERIFICATION.md).
