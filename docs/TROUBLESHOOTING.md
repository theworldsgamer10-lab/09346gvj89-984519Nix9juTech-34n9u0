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

> Note: this repo uploads through `scripts/youtube_upload.py`. Upstream's
> Upload-Post integration does **not** apply — the CLI has no publish code path,
> so `upload_post_*` keys in `config.toml` do nothing on this route.

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
