# Troubleshooting

Everything here was verified against MoneyPrinterTurbo `cli.py` and
`app/paths.py` at the time of writing, not guessed.

---

### `::error::no rendered mp4 found`
The render step exited before writing video. Look at the **Render video** log.

| Symptom above it | Cause | Fix |
|---|---|---|
| `401` / `invalid api key` | wrong `LLM_API_KEY` for the chosen provider | check provider + key pair |
| `No materials found` | stock key missing or rate-limited | check `PEXELS_API_KEY`; lower `material_concurrency` |
| `ffmpeg not found` | apt step skipped | re-run; it installs ffmpeg every time |
| killed at 75 min | very slow footage download | lower `--video-count`, raise `timeout-minutes` |

The step also prints the task directory contents on failure, so the real error
is always a few lines above.

---

### Upload never happens, but the run is green
By design. Publishing requires **both**:

- `publish: true` on a manual run, **or** repo variable `AUTO_PUBLISH=true`
- secrets `YT_CLIENT_ID` / `YT_CLIENT_SECRET` / `YT_REFRESH_TOKEN`

The **Verify YouTube credentials** step is the tell: if it is skipped, the
condition was false. If it runs and fails, the credentials are wrong.

### Correcting a common claim: does the CLI upload?

Measuring this properly, because it is easy to get wrong:

- `cli.py` has **no upload flags** and never mentions `upload_post`. True.
- But `cli.py` calls `app.services.task.start()`, and `start()` finishes by
  calling `_schedule_cross_post()`, which submits the upload to a
  `ThreadPoolExecutor` (2 workers) **and returns immediately**. The CLI prints
  its summary and the process exits.

So built-in Upload-Post publishing *can* fire from a CLI run, but nothing joins
that thread and there is no exit hook. In a short-lived CI process it is a race:
the upload may be killed mid-flight, and the run still reports success. That is
why this repo uploads with `scripts/youtube_upload.py` (synchronous, waits for
the video ID) instead of relying on the background thread.

Upstream's built-in path also requires an Upload-Post account (free tier: 10
uploads/month) and needs `upload_post_enabled` + `upload_post_auto_upload` +
`upload_post_platforms = ["youtube"]`. The direct API route is free at ~6
uploads/day and needs no third party.

---

### `redirect_uri_mismatch` or `invalid_grant` during `--auth`
- Use client type **Desktop app**, not "Web application".
- `invalid_grant` = the refresh token was revoked, or the OAuth consent screen is
  still in *Testing* and the token aged past 7 days. Publish the consent screen
  or re-run `--auth`.

---

### Topic repeats too early
`state/used.json` is committed by the workflow. If the "Commit topic history"
step warns that it could not push, the next run re-picks the same subject. Fix
branch protection on `main` (allow `github-actions[bot]`) or run from a branch
where the bot can push.

Manual reset:

```bash
git checkout -b reset-topics && git checkout main -- . 2>/dev/null
echo '{"used": []}' > state/used.json
git commit -am "reset topics" && git push origin reset-topics
```

---

### Thumbnail warning: `thumbnail rejected`
YouTube only allows custom thumbnails on **verified** channels (phone
verification, 2 min). Until then the step warns instead of failing — expected,
not a bug.

---

### Everything works but videos look bad
Normal for the first ten. In order of impact:

1. **Script quality** — edit the `BASE_PROMPT` in `scripts/pick_topic.py`.
   Sharpen the hook; that is what decides retention.
2. **Voice** — `en-US-AndrewNeural` is a safe default. `en-US-BrianNeural` is
   warmer, `en-US-AvaNeural` brighter. Set `VOICE_NAME`.
3. **Footage** — Pexels matches search terms loosely. Fewer, longer clips
   (`--video-clip-duration 5`) look calmer than rapid cuts.
4. **Thumbnail** — replace the extracted frame. Biggest click-through lever.

---

### `GitHub Actions minutes are exhausted`
A private repo gets 2,000 min/month. At 15–25 min per render, 2/day is roughly
60–100 min/day = 1,800–3,000/month. Either drop to 1/day, make the repo public
(unlimited), or move to a self-hosted runner.

---

### Is this against GitHub's terms?
Actions is licensed for "the production, testing, deployment, or publication of
the software project associated with the repository". A daily content factory is
a grey area and accounts have been suspended for cron abuse. Staying at low
volume with a real documented project is the practical mitigation; a $5 VPS
runner removes the question entirely.
