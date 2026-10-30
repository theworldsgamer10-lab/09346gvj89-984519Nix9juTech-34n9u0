# One-time setup

Total time: about 25 minutes. Do it on a laptop if you can — the OAuth step
opens a browser, which is painful on a phone.

Nothing here costs money.

---

## 1. Repo secrets (required, ~6 min)

Get the keys:

| Secret | Where | Notes |
|---|---|---|
| `LLM_API_KEY` | [console.groq.com/keys](https://console.groq.com/keys) | Free. This writes the scripts. |
| `PIXABAY_API_KEY` | [pixabay.com/api/docs](https://pixabay.com/api/docs/) | Free, instant. This supplies footage. |

**Already added secrets with the old names?** Nothing to redo. The workflow
accepts `MPT_LLM_API_KEY`, `MPT_PIXABAY_KEYS` and `MPT_PEXELS_KEYS` as
alternatives, and stock keys may be comma-separated. Pixabay is the default
`VIDEO_SOURCE` because you already hold that key; switch to `pexels` with the
`VIDEO_SOURCE` variable whenever you like.

Add them: **repo → Settings → Secrets and variables → Actions → New repository
secret**. Names must match exactly.

Fallbacks if you prefer: `LLM_PROVIDER=gemini` + a Google AI Studio key, or
`VIDEO_SOURCE=pixabay` + a Pixabay key. Set the provider as a **variable**
(Settings → Variables), the key as a **secret**.

---

## 2. Repo variables (optional)

Settings → Secrets and variables → Actions → **Variables** tab:

| Variable | Default | What it does |
|---|---|---|
| `LLM_PROVIDER` | `groq` | `groq` \| `gemini` \| `openrouter` \| `deepseek` \| `pollinations` |
| `LLM_MODEL` | `llama-3.3-70b-versatile` | model name for that provider |
| `VIDEO_SOURCE` | `pexels` | `pexels` \| `pixabay` \| `coverr` |
| `VOICE_NAME` | `en-US-AndrewNeural` | any Edge voice, see `docs/VOICES.md` |
| `AUTO_PUBLISH` | `false` | set `true` only when you trust the output |

---

## 3. YouTube upload (~15 min, only when you want it hands-off)

This is the fiddly part. Skip it and upload the artifact manually for the first
week — it takes two minutes per video and it teaches you what to fix.

### 3a. Google Cloud project

1. [console.cloud.google.com](https://console.cloud.google.com) → new project.
2. **APIs & Services → Library → YouTube Data API v3 → Enable**.
3. **OAuth consent screen** → External → fill the required fields → add your own
   Google account under **Test users**.
   *This is why Google keeps asking for a privacy policy and terms page — the
   repo ships `docs/privacy.md` and `docs/terms.md` you can host on GitHub Pages.*
4. **Credentials → Create credentials → OAuth client ID → Desktop app**.
5. Copy the **client ID** and **client secret**.

### 3b. Mint the refresh token (on your own machine)

```bash
pip install google-auth-oauthlib google-api-python-client
export YT_CLIENT_ID='...'
export YT_CLIENT_SECRET='...'
python scripts/youtube_upload.py --auth
```

It opens a browser, you approve, and it prints three values. Add them as
secrets: `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`.

> The refresh token is a password. It does not expire unless you revoke it, so
> revoke it at [myaccount.google.com/permissions](https://myaccount.google.com/permissions)
> if you ever paste it somewhere you regret.

### 3c. Verify the credentials without uploading

Workflow → Run workflow → `publish: true`, `dry_run: true`. The
"Verify YouTube credentials" step calls `channels().list(mine=True)` and prints
your channel name. If that step is green, publishing works.

---

## 4. Recommended warm-up order

| Run | Settings | Why |
|---|---|---|
| 1 | `dry_run: true` | proves secrets, config and topic pick |
| 2 | `publish: false` | real render; download the artifact and watch it |
| 3 | `publish: true, privacy: private` | checks upload path end to end |
| 4+ | set `AUTO_PUBLISH=true` + `privacy` default | only now go hands-off |

---

## 5. Costs check

Every service above is free at 2 videos/day. The two limits you could
realistically hit:

- **GitHub Actions minutes** — ~15–25 min per run. On a *private* repo that is
  60–100 min/day against 2,000/month, so ~2 videos/day fits. A public repo is
  unlimited.
- **YouTube quota** — upload costs 1,600 of 10,000 units/day. Shorts count the
  same. Ceiling is 6 uploads/day, far above your cadence.
