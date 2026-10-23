# Roadmap

- [x] Independent Python package and CLI
- [x] Validate JSON edit plans, immutable media paths and non-overlapping video clips
- [x] Local FFmpeg cutting, timeline gaps, speed, audio mix, SRT burn and MP4 export
- [x] Direct StepAudio 2.5 ASR text-only SSE adapter with source-bound result caching and no automatic retry
- [x] Openverse audio metadata/CC filters
- [x] External Jianying adapter and basic-plan conversion with native safety gates left intact
- [x] External yichen-asr router adapter
- [x] Offline tests and CI
- [ ] Step file-ASR timestamp route + full speech-to-edit timeline compiler (requires current provider documentation, live verification)
- [ ] Agent semantic cut planner with keep/delete explanations and protected-number/sentence windows
- [ ] Forced alignment and word-level caption generation (do not fabricate from text-only ASR)
- [ ] Video/B-roll overlay compositing, keyframes, transitions and richer title styles in cross-platform renderer
- [ ] Openverse audio asset download with verification, attribution manifest and explicit license approval
- [ ] Mac Jianying native compatibility acceptance matrix with authorized runtime; tests for 11.4/11.5/11.6
- [ ] UI/UX application, job queue and isolated worker runtime
- [ ] Multi-language dubbing, game-promo/video-to-shorts presets, output QC including listening and frame comparisons
