# Nix Tech — automated educational Shorts

A GitHub Actions pipeline that picks a topic, writes a script, voices it, cuts
stock footage to the narration, burns in subtitles, renders a vertical MP4, and
optionally uploads it to YouTube — twice a day, on free infrastructure.

```
cron 08:00 / 17:00 Dhaka
        │
        ▼
  pick_topic.py ──► curriculum.json (22 subjects, 176 topics, round-robin)
        │
        ▼
  prepare_config.py ──► .mpt/config.toml (patched from upstream template)
        │
        ▼
  mpt cli ──► script (LLM) ──► TTS (Edge) ──► footage (Pexels) ──► video
        │
        ▼
  make_metadata.py ──► title / description / tags / AI disclosure
        │
        ▼
  youtube_upload.py ──► YouTube Data API v3   (only when publish is on)
                        own Cloud project, no third party, no monthly cap
        │
        ▼
  state/used.json committed back ──► next run picks a different subject
```

## What this is not

- **It is not a long-form video maker.** MoneyPrinterTurbo produces 45–60 second
  clips: one paragraph of narration over stock footage. Educational explainer
  quality is real, but depth is capped by the format.
- **It does not fact-check.** The LLM writes the script unattended. The prompt
  is written to suppress invented numbers ("if a number is uncertain, leave it
  out"), which reduces the failure rate — it does not eliminate it. Read the
  first month of scripts before they go public.
- **It does not design thumbnails.** It grabs a frame from the video. A designed
  thumbnail is worth more click-through than anything else in this repo.

## Quick start

```bash
git clone <your-repo> && cd <your-repo>
cp .env.example .env          # fill in keys
./scripts/deploy.sh --check   # verify everything locally, no API calls
```

Then add the secrets (see `docs/SETUP.md`) and hit **Actions → Daily educational
short → Run workflow** with `dry_run: true` first.

## Layout

```
.github/workflows/daily-short.yml   the pipeline
scripts/pick_topic.py               topic rotation + per-subject teaching persona
scripts/prepare_config.py           builds .mpt/config.toml from secrets
scripts/make_metadata.py            title / description / tags
scripts/youtube_upload.py           upload + OAuth bootstrap
scripts/ci.py                       workflow glue (GITHUB_OUTPUT, field reads)
scripts/deploy.sh                   local preflight + push helper
topics/curriculum.json              22 domains, 176 topics, ordered by difficulty
state/used.json                     history; committed back by the workflow
config/mpt-config.template.toml     vendored copy of upstream's 845-line template
tests/                              topic picker tests
docs/SETUP.md                       quick secrets setup
docs/OWN-API-SETUP.md               full Google Cloud walkthrough, every form field
docs/YOUTUBE-CREDENTIALS.md         the App-domain form answers
docs/site/                          home page + privacy + ToS for GitHub Pages
docs/TROUBLESHOOTING.md             what breaks and what to do
```

## Cost

| Item | Tier | Limit that matters |
|---|---|---|
| GitHub Actions | free | 2,000 min/mo private; ~15–25 min per video |
| Groq (LLM) | free | generous daily request cap |
| Pexels / Pixabay | free | 200 req/hr / 100 req/min |
| Edge TTS | free | no key, no quota |
| YouTube Data API | free | 100 uploads/day (own bucket since Jun 2026) |
| **Total** | **$0** | 2 videos/day is well inside every limit |

## Honest limits

1. **GitHub Actions ToS.** Actions is for building, testing and deploying *this
   software*. Running it as a daily content factory is a grey area, and accounts
   have been suspended for cron abuse. Keep it at 1–2 videos/day, keep the repo a
   real documented project, and be ready to move to a $5 VPS runner if you scale.
2. **YouTube's inauthentic-content policy.** Mass-produced AI video with no
   added value can be denied monetisation. What protects you: a consistent
   subject, a real teaching persona per domain, and reviewing output. What
   doesn't: publishing 8 videos a day and hoping.
3. **Stock footage mismatches.** Pexels returns whatever matches the search
   terms. A video about entropy may show a kettle. Acceptable for Shorts,
   noticeable on serious topics.

## License

Your repo, your call. MoneyPrinterTurbo is MIT; the vendored template keeps its
upstream licence.
