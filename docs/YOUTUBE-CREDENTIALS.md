# YouTube credentials — the exact form answers

You asked two things: what to put in the **App domain** form, and whether your
videos really get forced private. Both answers below are checked against
Google's current documentation, not memory.

---

## First: the thing that decides everything

**Uploads from a Google Cloud project created after 28 July 2020 are locked to
private until that project passes YouTube's compliance audit.** Setting
`privacyStatus: public` does not override it, and the API returns no error — the
video simply lands private, and you get an email later.

From Google's own `videos.insert` reference:

> *"All videos uploaded via the videos.insert endpoint from unverified API
> projects created after 28 July 2020 will be restricted to private viewing
> mode. To lift this restriction, each API project must undergo an audit."*

So if your previous automations published publicly, they were almost certainly
using an **already-audited** project or a third-party service whose app is
audited — not their own fresh Cloud project. The policy is real; the workaround
is what people don't mention.

**What this means for you, concretely:**

| Route | Public uploads | Cost | Setup |
|---|---|---|---|
| **Upload-Post** (default here) | ✅ works immediately — their app is audited | 10/month free, then ~$10/mo | 5 min, 2 secrets |
| **Your own API** | ❌ private until audit passes; no published ETA | free | 20 min + audit form |
| Your own API **after** audit | ✅ | free | weeks of waiting, may not be approved |

The workflow uses Upload-Post by default for exactly this reason. Your own API
route still exists — set the repo variable `PUBLISH_VIA=youtube_api` — and is
worth doing *in parallel*: submit the audit form, and if it clears, switch over
and stop paying.

---

## The App domain form

This form only matters if you're setting up your own OAuth project (the
`PUBLISH_VIA=youtube_api` route). Upload-Post needs none of it.

The repo now contains a ready site at `docs/site/`. One-time turn-on:

1. Repo → **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: **main**, folder: **`/docs`** → Save
4. Wait ~60 seconds. Your URLs become:

```
https://<your-username>.github.io/<your-repo>/site/
https://<your-username>.github.io/<your-repo>/site/privacy.html
https://<your-username>.github.io/<your-repo>/site/terms.html
```

### Field-by-field

| Field | Paste this |
|---|---|
| **Application home page** | `https://<username>.github.io/<repo>/site/` |
| **Application privacy policy link** | `https://<username>.github.io/<repo>/site/privacy.html` |
| **Application Terms of Service link** | `https://<username>.github.io/<repo>/site/terms.html` |
| **Authorised domains** | `github.io` |
| **App name** | `Nix Tech` |
| **User support email** | your Gmail |
| **Developer contact email** | your Gmail |

Notes that save you an hour of confusion:

- **`github.io` is a public suffix owned by GitHub.** You cannot verify it in
  Search Console, so Google will *not* grant brand verification on a
  `*.github.io` URL. That is fine — verification is only needed to remove the
  "unverified app" warning. For **personal use, Google explicitly exempts you
  from verification** ("if you are the only user of your app"). You click
  through the warning once and you're done.
- **If the form rejects `github.io` in Authorised domains**, leave that field
  blank and save. It is only enforced for brand verification.
- Prefer a real domain? Point a $10/yr domain at GitHub Pages and you can verify
  it. Not required to get running.

### Don't skip this

**Publish the app:** Audience → **Publish app** → status becomes *In production*.

Left in *Testing*, Google kills your refresh token after **7 days** and the
pipeline wakes up dead with `invalid_grant` every week. Publishing to production
does not require verification for a single-user app.

---

## Getting the refresh token

Two options; the second is the one that actually works today.

### Option A — browser flow (recommended)

On a laptop:

```bash
pip install google-auth-oauthlib google-api-python-client
export YT_CLIENT_ID='...'
export YT_CLIENT_SECRET='...'
python scripts/youtube_upload.py --auth
```

A browser opens, you approve with the **channel's** Google account, and it prints
the three secret values.

### Option B — no terminal

Google retired the `urn:ietf:wg:oauth:2.0:oob` ("copy this code") flow, so skip
anything that tells you to use it. Use the loopback flow above, or:

1. Open this URL with your client ID substituted:
   `https://accounts.google.com/o/oauth2/v2/auth?client_id=YOUR_ID&redirect_uri=http://localhost&response_type=code&scope=https://www.googleapis.com/auth/youtube.upload&access_type=offline&prompt=consent`
2. Approve. The browser lands on `http://localhost/?code=...` and fails to load —
   that's expected.
3. Copy the `code` value out of the address bar.
4. Exchange it:

```bash
curl -s -X POST https://oauth2.googleapis.com/token \
  -d client_id=YOUR_ID -d client_secret=YOUR_SECRET \
  -d code=THE_CODE -d grant_type=authorization_code \
  -d redirect_uri=http://localhost
```

The `refresh_token` in the response is the value you need.

### Then add three secrets

`YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`

Revoke any time at [myaccount.google.com/permissions](https://myaccount.google.com/permissions).

---

## Verify before trusting it

Workflow → Run workflow → `publish: true`, `dry_run: true`. The
**Verify publisher credentials** step prints either your channel name (API
route) or confirmation that Upload-Post is wired (default route). Green means the
credentials work; it uploads nothing.
