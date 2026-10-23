# Batch edits and recovery

Create a UTF-8 manifest. Paths are relative to the manifest's directory unless absolute. The batch compiler validates the manifest, media, timings and request shape before processing jobs. Each job has a unique portable name and its own pipeline cache/plan/report/output. Jobs execute sequentially to bound CPU/memory usage; one failed job does not hide successful exports.

```json
{
  "schema": "video-clips/batch/v1",
  "jobs": [
    {
      "name": "tutorial",
      "source": "tutorial.mp4",
      "srt": "tutorial.srt",
      "instruction": "Remove hesitations and preserve the full argument",
      "strategy": "standard",
      "protected_terms": ["VIDEO-Clips"],
      "aspect": "9:16",
      "target_ms": 180000,
      "model": {
        "endpoint": "https://your-provider.example/v1/chat/completions",
        "model": "your-model",
        "max_tokens": 16000
      }
    },
    {
      "name": "offline-clip",
      "source": "second.mp4",
      "step_file": "second.completed-asr.json",
      "instruction": "Keep the key points",
      "response": "second.agent-decisions.json"
    }
  ]
}
```

```bash
video-clips batch-edit batch.json --workdir work/batch-a --render
# For authorized model requests, add --allow-paid-model.
# To execute policy-permitted semantic exclusions, add --apply-ai-cuts.
# Resume identical inputs and settings with the same command plus --resume.
```

Model credentials remain in the environment (default `VIDEO_CLIPS_MODEL_KEY`); the manifest never self-authorizes paid calls or automatic cuts. Every live model request requires the corresponding top-level command flag. Offline `response` and `model` are mutually exclusive. Supported optional fields are `channel` (Step import), `music` and `music_volume` (local media only). Single-edit limits and protection rules also apply to each batch job.

`batch.json` in the output directory records per-job success/failure and the overall result. The command exits 2 if any job failed. On resume, each job's source/transcript/options fingerprint and model pending/cache state are enforced. Successful model calls are not repeated; local rendering can run again. Changed manifest/settings require a new batch directory. An uncertain model submission still requires billing/provider inspection before a paid retry. After a hard crash, confirm workers stopped before clearing `.batch-running` or per-job `.running` locks.

This is a local sequential manifest runner, not a distributed scheduler, concurrent GPU queue or automatic paid retry service. A duration target may remain unmet when protected content must survive.
