# Roadmap — 0.2.0a1

## Implemented

- [x] Independent Python package, CLI and strict vendor-neutral JSON timeline
- [x] FFmpeg trim/concatenation, gaps, speed, original/mixed audio, SRT burn and MP4
- [x] Source overwrite/hard-link and source-range guards; globally bounded frame clock
- [x] Export canvas/fps/decoded-frame/A-V timing checks and complete decode verification
- [x] StepAudio text-only SSE with language/source-bound cache, normalization and uncertain-submission guard
- [x] Completed Step file-ASR timestamp import, channel/overlap guards and SRT conversion
- [x] Frame-aligned speech rough cuts, exact cue remapping and explainable removed ranges
- [x] Transcript fingerprint, strict AI decision contract and editable review proposals
- [x] Executable compatible-model Agent with conservative/standard/aggressive/highlights strategies
- [x] Independent numeric/term/context/category/confidence policy and explicit auto-apply
- [x] Bounded model requests, explicit network/cost opt-in, cached successful response and recoverable job manifest
- [x] Authenticated loopback UI with import/preview, timed-caption editing, Agent settings, music and real exports
- [x] Sequential persisted UI jobs and reversible review/restoration child versions
- [x] Browser workflow, actual MP4 download and desktop/mobile overflow acceptance (CI run 39986291653)
- [x] Batch manifest CLI with independent job state, partial-failure reporting and recovery
- [x] Repository-local bootstrap, Python wheel assets, authored Agent Skill and synthetic-media smoke
- [x] External Jianying basic-plan adapter and authorized Yichen router integration
- [x] Openverse audio metadata search with commercial-license filters

## Active release gates

- [ ] Windows/macOS/Linux FFmpeg + package matrix: configured; record actual results after CI completes
- [ ] Paid model/ASR provider acceptance with approved credentials and cost limits (tests currently use local fixtures/mocks)
- [ ] Automatic file-ASR submit/query/recovery and raw-video-only end-to-end operation
- [ ] Forced alignment and reliable word-level timestamps where utterance timing is insufficient
- [ ] Multitrack video/B-roll/picture-in-picture, transitions, keyframes and richer caption styling/animation
- [ ] Multiple independent highlight exports, semantic rearrangement and content presets
- [ ] Licensed sound-effect acquisition/attribution verification and automatic music scheduling/ducking
- [ ] Isolated process workers, cancellation and bounded persistent queue policies for larger local installations
- [ ] Authorized native Jianying runtime/draft/export compatibility matrix; GUI and true headless paths reported separately
- [ ] Human/perceptual cut, ASR accuracy and lip-sync acceptance beyond structural media checks

The current UI timeline displays and seeks retained segments; it does not claim drag editing or arbitrary multitrack manipulation. Aspect conversion fits and pads; it does not claim automatic face tracking. Targets are advisory when meaning/content protection prevents further cuts. Alpha packaging is not a declaration that all release gates are complete.
