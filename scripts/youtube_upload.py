#!/usr/bin/env python3
"""Upload a rendered video to YouTube with the YouTube Data API v3.

Why this exists
---------------
MoneyPrinterTurbo's CLI has no publishing step at all (verified: no
`upload_post` reference anywhere in cli.py). Upstream's Upload-Post integration
lives in the web task pipeline, and its free tier is 10 uploads/month - short of
1-2/day. This script talks to YouTube directly instead: free, ~6 uploads/day
inside Google's default project quota, and no third party in the loop.

Credentials
-----------
Needs an OAuth *refresh token* (not an API key). You create it once on your own
machine with `python scripts/youtube_upload.py --auth` and paste the printed
values into GitHub Secrets. The refresh token is long-lived; the access token
is minted here, in memory, and never stored.

Env vars:
  YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN   (required)
  YT_PRIVACY            public | unlisted | private   (default: private)
  YT_CATEGORY_ID        default 27 (Education)
  YT_MADE_FOR_KIDS      true | false                  (default: false)

Usage:
  python scripts/youtube_upload.py --auth                 # one-time, on your PC
  python scripts/youtube_upload.py --file out/x.mp4 --title "..." \
      --description-file out/description.txt --tags a,b,c \
      --thumbnail out/thumb.png --playlist PLxxxx
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]
TOKEN_URI = "https://oauth2.googleapis.com/token"


def die(msg: str) -> None:
    print(f"::error::{msg}", file=sys.stderr)
    raise SystemExit(1)


# --------------------------------------------------------------------------- auth


def run_local_auth() -> int:
    """Interactive one-time flow. Run this on your own machine, not in CI."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        die("pip install google-auth-oauthlib")

    client_id = os.environ.get("YT_CLIENT_ID", "").strip()
    client_secret = os.environ.get("YT_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        die("set YT_CLIENT_ID and YT_CLIENT_SECRET before running --auth")

    # Desktop-app client config, built in memory so no client_secret.json file
    # is left lying on disk.
    config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": TOKEN_URI,
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(config, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")

    if not creds.refresh_token:
        die("Google did not return a refresh token. Remove the app's access at "
            "https://myaccount.google.com/permissions and run again.")
    print("\n" + "=" * 62)
    print("Add these as GitHub repository secrets:")
    print("=" * 62)
    print(f"YT_CLIENT_ID     = {creds.client_id}")
    print(f"YT_CLIENT_SECRET = {creds.client_secret}")
    print(f"YT_REFRESH_TOKEN = {creds.refresh_token}")
    print("=" * 62)
    print("Treat the refresh token like a password. Revoke it at")
    print("https://myaccount.google.com/permissions whenever you want.\n")
    return 0


def get_service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    cid = os.environ.get("YT_CLIENT_ID", "").strip()
    secret = os.environ.get("YT_CLIENT_SECRET", "").strip()
    refresh = os.environ.get("YT_REFRESH_TOKEN", "").strip()
    missing = [n for n, v in [("YT_CLIENT_ID", cid), ("YT_CLIENT_SECRET", secret),
                              ("YT_REFRESH_TOKEN", refresh)] if not v]
    if missing:
        die(f"missing secrets: {', '.join(missing)} - see docs/YOUTUBE-SETUP.md")

    creds = Credentials(
        token=None,
        refresh_token=refresh,
        token_uri=TOKEN_URI,
        client_id=cid,
        client_secret=secret,
        scopes=SCOPES,
    )

    # Mint an access token up front. Without this, a bad client id or a revoked
    # refresh token surfaces as a raw RefreshError traceback from deep inside
    # the client library, which reads like a code bug instead of a credential
    # problem.
    try:
        import google.auth.transport.requests as google_requests
        from google.auth.exceptions import RefreshError

        creds.refresh(google_requests.Request())
    except RefreshError as exc:
        detail = str(exc)
        if "invalid_client" in detail:
            hint = "YT_CLIENT_ID / YT_CLIENT_SECRET are wrong, or the OAuth client was deleted."
        elif "invalid_grant" in detail:
            hint = ("the refresh token was revoked or expired. If the consent screen is "
                    "still in Testing, tokens die after 7 days - publish the app, then "
                    "re-run: python scripts/youtube_upload.py --auth")
        else:
            hint = "re-run: python scripts/youtube_upload.py --auth"
        die(f"YouTube auth failed - {hint}\n  detail: {detail}")
    except Exception as exc:  # network, DNS, clock skew
        die(f"could not reach Google to refresh the token: {exc}")

    return build("youtube", "v3", credentials=creds, cache_discovery=False)


# --------------------------------------------------------------------------- upload


def upload(args: argparse.Namespace) -> int:
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    path = Path(args.file)
    if not path.exists():
        die(f"video not found: {path}")
    if path.stat().st_size == 0:
        die(f"video is empty: {path}")

    title = args.title.strip()
    if not title:
        die("--title is empty")
    # YouTube hard limit; truncate rather than let the API reject the upload.
    if len(title) > 100:
        title = title[:97].rstrip() + "..."
        print(f"title truncated to 100 chars: {title}")

    description = ""
    if args.description_file:
        dp = Path(args.description_file)
        if dp.exists():
            description = dp.read_text(encoding="utf-8").strip()
    if args.description:
        description = args.description
    if len(description) > 4900:  # API limit is 5000 incl. tags
        description = description[:4900].rsplit(" ", 1)[0] + "..."

    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()][:30]

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": str(args.category),
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": args.privacy,
            "selfDeclaredMadeForKids": args.made_for_kids,
            "license": "youtube",
            "embeddable": True,
        },
    }

    service = get_service()

    # Dry run: prove the credentials work without burning a quota slot or
    # publishing anything.
    if args.dry_run:
        try:
            ch = service.channels().list(part="snippet,statistics,mine", mine=True).execute()
        except HttpError as exc:
            die(f"YouTube rejected the credentials: {exc}")

        items = ch.get("items") or []
        if not items:
            die("The credentials work, but this Google account has no YouTube channel. "
                "Sign in to youtube.com with the same account and create a channel, "
                "then re-run --auth so the token is issued for the channel account.")
        item = items[0]
        name = item.get("snippet", {}).get("title", "<unknown>")
        subs = item.get("statistics", {}).get("subscriberCount", "?")
        vids = item.get("statistics", {}).get("videoCount", "?")
        print(f"::notice::DRY RUN OK - authenticated as '{name}' ({subs} subs, {vids} videos)")
        print(f"  video : {path.name} ({path.stat().st_size / 1e6:.1f} MB)")
        print(f"  title : {title}")
        print(f"  priv  : {args.privacy}")
        print(f"  tags  : {', '.join(tags) or '(none)'}")
        return 0

    privacy = args.privacy
    if args.schedule:
        # Scheduling requires privacyStatus=private at upload time.
        body["status"]["privacyStatus"] = "private"
        body["status"]["publishAt"] = args.schedule
        privacy = f"private until {args.schedule}"

    actual = "not-checked"
    media = MediaFileUpload(str(path), mimetype="video/mp4",
                            chunksize=8 * 1024 * 1024, resumable=True)
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)

    print(f"uploading {path.name} ({path.stat().st_size / 1e6:.1f} MB) ...")
    response = None
    attempt = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                print(f"  {pct}% ({status.resumable_progress() / 1e6:.1f} MB sent)")
        except HttpError as exc:
            if exc.resp.status in (500, 502, 503, 504) and attempt < 5:
                attempt += 1
                print(f"  transient {exc.resp.status}, retry {attempt}/5 ...")
                continue
            die(f"upload failed: {exc}")

    vid = response["id"]
    print(f"::notice::uploaded https://youtu.be/{vid} ({privacy})")

    # ---- verify the privacy YouTube actually applied --------------------
    # Google's docs contradict each other on this. The videos.insert reference
    # (updated Oct 2026) says unverified projects are NOT restricted to private;
    # the July 2020 revision history says they are, until an audit. Both pages
    # are live. Rather than trust either, read the stored value back and report
    # what actually happened.
    if not args.schedule and args.privacy in {"public", "unlisted"}:
        try:
            check = service.videos().list(part="status", id=vid).execute()
            items = check.get("items") or []
            actual = items[0].get("status", {}).get("privacyStatus", "unknown") if items else "unknown"
            upload_state = items[0].get("status", {}).get("uploadStatus", "") if items else ""
            if actual == args.privacy and upload_state in ("", "uploaded", "processed"):
                print(f"::notice::privacy confirmed: {actual}")
            elif actual == "private":
                print("::error::requested " + args.privacy + " but YouTube stored the video as "
                      "PRIVATE. This is the unaudited-project restriction. The video is live at "
                      "https://youtu.be/" + vid + " but only you can see it.")
                print("::error::Fix: submit the YouTube API compliance audit, then re-run. "
                      "Until it passes, publish with pubkey=upload_post or flip each video "
                      "to public in YouTube Studio.")
            else:
                print(f"::warning::privacy is '{actual}', expected '{args.privacy}' "
                      f"(uploadStatus={upload_state or 'n/a'})")
        except HttpError as exc:
            print(f"::warning::could not verify privacy: {exc}")

    if args.thumbnail:
        tp = Path(args.thumbnail)
        if tp.exists():
            try:
                service.thumbnails().set(
                    videoId=vid,
                    media_body=MediaFileUpload(str(tp), mimetype="image/png"),
                ).execute()
                print(f"  thumbnail set from {tp.name}")
            except HttpError as exc:
                # Not fatal: an unverified channel cannot set custom thumbnails.
                print(f"::warning::thumbnail rejected (channel may not be verified): {exc}")
        else:
            print(f"::warning::thumbnail not found: {tp}")

    if args.playlist:
        try:
            service.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": args.playlist,
                        "resourceId": {"kind": "youtube#video", "videoId": vid},
                    }
                },
            ).execute()
            print(f"  added to playlist {args.playlist}")
        except HttpError as exc:
            print(f"::warning::playlist insert failed: {exc}")

    summary = Path(args.report)
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text(json.dumps({
        "provider": "youtube-data-api",
        "video_id": vid,
        "title": title,
        "url": f"https://youtu.be/{vid}",
        "privacy_requested": args.privacy,
        "privacy_actual": actual,
        "note": ("private despite a public request = unaudited project; "
                 "submit the compliance audit" if actual == "private" else ""),
    }, indent=2), encoding="utf-8")
    print(f"wrote {summary}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Upload a video to YouTube")
    ap.add_argument("--auth", action="store_true", help="one-time local OAuth flow")
    ap.add_argument("--file", help="path to mp4")
    ap.add_argument("--title", default="")
    ap.add_argument("--description", default="")
    ap.add_argument("--description-file", default="")
    ap.add_argument("--tags", default="")
    ap.add_argument("--thumbnail", default="")
    ap.add_argument("--playlist", default="")
    ap.add_argument("--privacy", default=os.environ.get("YT_PRIVACY", "private"),
                    choices=["public", "unlisted", "private"])
    ap.add_argument("--category", default=os.environ.get("YT_CATEGORY_ID", "27"))
    ap.add_argument("--schedule", default="", help="ISO 8601 publishAt, e.g. 2026-11-01T08:00:00Z")
    ap.add_argument("--made-for-kids", action="store_true",
                    default=os.environ.get("YT_MADE_FOR_KIDS", "false").lower() == "true")
    ap.add_argument("--report", default="out/upload.json")
    ap.add_argument("--dry-run", action="store_true",
                    help="verify credentials and print the plan, upload nothing")
    args = ap.parse_args(argv)

    if args.auth:
        return run_local_auth()
    if not args.file:
        die("--file is required (or use --auth)")
    return upload(args)


if __name__ == "__main__":
    sys.exit(main())
