# Own API setup — every step, every form field

You chose your own Google Cloud project: no third party, no monthly cap.
`PUBLISH_VIA` already defaults to `youtube_api`, so once these five secrets
exist the workflow uses your project and nothing else.

Total time: ~25 minutes. Cost: $0.

---

## The one thing to know before you start

Google's own documentation contradicts itself on whether a new project can
upload publicly:

| Source | Says |
|---|---|
| `videos.insert` reference, updated **Oct 2026** | "Videos uploaded from unverified API projects are **not** restricted to private viewing mode." |
| API revision history, **28 July 2020** | Projects created after that date are "restricted to private viewing mode" until an audit. |

Both are live on Google's site today. Community reports in Oct 2026 are split —
some new projects upload public immediately, others land private.

**So this repo does not guess. `youtube_upload.py` reads `status.privacyStatus`
back from YouTube after every upload:**

- comes back `public`/`unlisted` → `::notice::privacy confirmed`
- comes back `private` when you asked for public → `::error::` explaining it's
  the unaudited-project lock, with the fix

You'll know on your first real upload which world you're in. No guessing.

---

## Step 1 — Create the project (2 min)

1. [console.cloud.google.com](https://console.cloud.google.com) → project
   dropdown → **New project**
2. Name: `nix-tech` → **Create**
3. Make sure the project selector shows `nix-tech` before continuing

## Step 2 — Enable the API (1 min)

**APIs & Services → Library** → search `YouTube Data API v3` → **Enable**

## Step 3 — OAuth consent screen (7 min)

Google renamed this to **Google Auth Platform**. Old tutorials point at
"OAuth consent screen"; the pages are **Branding**, **Audience**, **Clients**,
**Data Access**.

### Branding tab

| Field | Value |
|---|---|
| App name | `Nix Tech` |
| User support email | your Gmail |
| App logo | skip |
| Application home page | `https://<user>.github.io/<repo>/site/` |
| Application privacy policy | `https://<user>.github.io/<repo>/site/privacy.html` |
| Application terms of service | `https://<user>.github.io/<repo>/site/terms.html` |
| Authorised domains | `github.io` (or leave blank — optional) |
| Developer contact email | your Gmail |

The three URLs come from `docs/site/` in this repo. Turn on
**Settings → Pages → main → `/docs`** and wait ~60s for them to go live.
`github.io` cannot pass brand verification (GitHub owns the suffix), but for
personal single-user use Google **explicitly exempts you from verification** —
you click through the "unverified app" warning once.

### Audience tab

- User type: **External**
- **Publish app** → status becomes *In production*

⚠️ **Do not skip this.** In *Testing*, Google expires refresh tokens after
**7 days** and the pipeline dies weekly with `invalid_grant`.

### Data Access tab

- **Add or remove scopes** → search and tick: `.../auth/youtube.upload`
- Optional: `.../auth/youtube.readonly`

## Step 4 — Create the OAuth client (2 min)

**Clients → Create client → Application type: Desktop app** → name it `nix-tech-cli`
→ **Create**. Copy the **Client ID** and **Client secret**.

> Must be **Desktop app**. A "Web application" client will fail with
> `redirect_uri_mismatch` on the loopback flow below.

## Step 5 — Mint the refresh token (3 min)

On a laptop, in the repo folder:

```bash
pip install google-auth-oauthlib google-api-python-client
export YT_CLIENT_ID='...'
export YT_CLIENT_SECRET='...'
python scripts/youtube_upload.py --auth
```

Signs in with the **channel's** Google account (the one that owns the channel),
prints three values, exits.

**No terminal?** Use the loopback URL manually:

```
https://accounts.google.com/o/oauth2/v2/auth?client_id=YOUR_ID&redirect_uri=http://localhost&response_type=code&scope=https://www.googleapis.com/auth/youtube.upload&access_type=offline&prompt=consent
```

Approve → the browser fails to load `http://localhost/?code=...` (expected) →
copy the `code` from the address bar → exchange it:

```bash
curl -s -X POST https://oauth2.googleapis.com/token \
  -d client_id=YOUR_ID -d client_secret=YOUR_SECRET \
  -d code=THE_CODE -d grant_type=authorization_code \
  -d redirect_uri=http://localhost
```

Ignore any guide telling you to use `urn:ietf:wg:oauth:2.0:oob` — Google retired
that flow.

## Step 6 — Add three secrets (2 min)

Settings → Secrets and variables → Actions:

| Secret | Value |
|---|---|
| `YT_CLIENT_ID` | from step 4 |
| `YT_CLIENT_SECRET` | from step 4 |
| `YT_REFRESH_TOKEN` | from step 5 |

## Step 7 — Verify without uploading (2 min)

Actions → **Daily educational short** → **Run workflow**:

- `dry_run: false`
- `publish: true`
- `privacy: unlisted`

The **Verify publisher credentials** step calls `channels().list(mine=True)` and
prints your channel name. Watch what the upload step prints about privacy.

---

## Quota, current as of late 2026

The numbers changed twice recently, so older guides are wrong:

- **June 1, 2026:** `videos.insert` moved to its own quota bucket — **100
  uploads/day** at 1 unit each (was ~1,600 units of a shared 10,000, i.e. 6/day).
- Your 2/day cadence is nowhere near any limit.

## If uploads land private

1. Submit the **YouTube API Services Audit and Quota Extension Form**
   (linked from the API compliance audit docs). Free, no published timeline.
2. In the meantime, two options:
   - Set `YT_PRIVACY` / the `privacy` input to `private`, review in Studio, flip
     to public by hand (2 min/day), or
   - Set repo variable `PUBLISH_VIA=upload_post` as a temporary bridge — it
     publishes publicly right away, but allow 10 uploads/month free.

## Errors and what they mean

| Error | Meaning |
|---|---|
| `invalid_client` | wrong client ID/secret, or the client was deleted |
| `invalid_grant` | refresh token revoked, or consent screen was left in Testing (7-day expiry) |
| `redirect_uri_mismatch` | client type isn't "Desktop app" |
| `forbiddenPrivacySetting` | project restricted to private uploads — needs the audit |
| `quotaExceeded` | 100 uploads/day bucket empty until midnight PT |
| `youtubeSignupRequired` | that Google account has no YouTube channel |
