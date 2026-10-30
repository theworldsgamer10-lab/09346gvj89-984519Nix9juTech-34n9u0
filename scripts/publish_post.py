#!/usr/bin/env python3
"""Publish a video through Upload-Post - synchronously, with confirmation.

Why this exists next to youtube_upload.py
-----------------------------------------
The two routes solve different problems, and the difference is not cosmetic:

  youtube_upload.py   your own Google Cloud project.
                      Free, no third party, but projects created after
                      28 July 2020 have uploads forced to PRIVATE by YouTube
                      until the project passes the compliance audit. There is
                      no ETA on that audit.

  publish_post.py     Upload-Post (api.upload-post.com).
                      Their Google project is already audited, so public and
                      unlisted uploads work immediately. Free tier: 10
                      uploads/month. Past 10, either pay (~$10/mo) or wait for
                      your own audit.

MoneyPrinterTurbo already ships an Upload-Post integration, but it submits the
upload to a background ThreadPoolExecutor and returns without joining. In a
short-lived CI run the process can exit mid-upload while the run still reports
success. This script does the same HTTP calls but blocks until the platform
reports a terminal state, so "green" means "published".

Env:
  UPLOAD_POST_API_KEY    required
  UPLOAD_POST_USERNAME   required - your Upload-Post profile name
  UP_PRIVACY             public | unlisted | private   (default: unlisted)

Usage:
  python scripts/publish_post.py --file out/v.mp4 --title "..." \
      --description-file out/description.txt --tags a,b,c --platforms youtube
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

API_BASE = "https://api.upload-post.com"
POLL_INTERVAL = 10
POLL_TIMEOUT = 600  # 10 min; Shorts are ~20 MB and normally land in under one


def die(msg: str) -> None:
    print(f"::error::{msg}", file=sys.stderr)
    raise SystemExit(1)


def warn(msg: str) -> None:
    print(f"::warning::{msg}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Publish via Upload-Post")
    ap.add_argument("--file", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--description", default="")
    ap.add_argument("--description-file", default="")
    ap.add_argument("--tags", default="")
    ap.add_argument("--platforms", default="youtube", help="comma separated: youtube,tiktok,instagram")
    ap.add_argument("--privacy", default=os.environ.get("UP_PRIVACY", "unlisted"),
                    choices=["public", "unlisted", "private"])
    ap.add_argument("--made-for-kids", default="false")
    ap.add_argument("--synthetic", default="true",
                    help="disclose AI-generated media (YouTube requires this)")
    ap.add_argument("--report", default="out/upload.json")
    ap.add_argument("--no-wait", action="store_true", help="submit and exit without polling")
    args = ap.parse_args(argv)

    try:
        import requests
    except ImportError:
        die("pip install requests")

    api_key = os.environ.get("UPLOAD_POST_API_KEY", "").strip()
    username = os.environ.get("UPLOAD_POST_USERNAME", "").strip()
    if not api_key:
        die("UPLOAD_POST_API_KEY is empty - add it in repo Settings -> Secrets -> Actions")
    if not username:
        die("UPLOAD_POST_USERNAME is empty - this is your Upload-Post profile name, not your email")

    path = Path(args.file)
    if not path.exists():
        die(f"video not found: {path}")
    if path.stat().st_size == 0:
        die(f"video is empty: {path}")

    description = args.description
    if args.description_file:
        dp = Path(args.description_file)
        if dp.exists():
            description = dp.read_text(encoding="utf-8").strip()

    tags = [t.strip() for t in args.tags.split(",") if t.strip()][:30]
    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    request_id = str(uuid.uuid4())

    # multipart form. Field names mirror app/services/upload_post.py upstream.
    data: list[tuple[str, str]] = [
        ("user", username),
        ("request_id", request_id),
        ("title", args.title[:2200]),
        ("privacy_level", args.privacy),
    ]
    for p in platforms:
        data.append(("platform[]", p))
    if any(p.startswith("youtube") for p in platforms):
        data.append(("selfDeclaredMadeForKids", str(args.made_for_kids).lower()))
        data.append(("privacyStatus", args.privacy))
        data.append(("youtube_title", args.title[:100]))
        if description:
            data.append(("youtube_description", description))
        for t in tags:
            data.append(("tags[]", t))
        if args.synthetic == "true":
            data.append(("containsSyntheticMedia", "true"))

    print(f"submitting {path.name} ({path.stat().st_size / 1e6:.1f} MB) to {', '.join(platforms)}")
    print(f"  request_id: {request_id}")
    try:
        with path.open("rb") as fh:
            resp = requests.post(
                f"{API_BASE}/api/upload",
                headers={"Authorization": f"Apikey {api_key}"},
                data=data,
                files={"video": fh},
                timeout=300,
                allow_redirects=False,
            )
    except requests.exceptions.RequestException as exc:
        die(f"cannot reach Upload-Post: {exc}")

    if resp.status_code >= 400:
        body = resp.text[:400].replace("\n", " ")
        hint = ""
        if resp.status_code == 401:
            hint = " (API key rejected - check UPLOAD_POST_API_KEY)"
        elif resp.status_code == 403:
            hint = " (key lacks permission, or the monthly upload allowance is used up)"
        die(f"Upload-Post returned HTTP {resp.status_code}{hint}: {body}")

    try:
        payload = resp.json()
    except ValueError:
        payload = {}

    if payload.get("success") is False:
        die(f"Upload-Post rejected the upload: {json.dumps(payload)[:400]}")

    print(f"  accepted (HTTP {resp.status_code})")

    if args.no_wait:
        print("::notice::submitted without waiting; check Upload-Post dashboard")
        return _finish(args, request_id, platforms, "submitted")

    # ---- poll for a terminal result -------------------------------------
    deadline = time.time() + POLL_TIMEOUT
    last = ""
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        try:
            r = requests.get(
                f"{API_BASE}/api/uploadposts/status",
                params={"request_id": request_id},
                headers={"Authorization": f"Apikey {api_key}"},
                timeout=30,
            )
            state = r.json()
        except (requests.exceptions.RequestException, ValueError) as exc:
            print(f"  status poll error ({type(exc).__name__}), retrying")
            continue

        results = state.get("results")
        summary = json.dumps(state)[:200]
        if summary != last:
            print(f"  status: {summary}")
            last = summary

        ok, failed, done = _interpret(results, platforms)
        if ok:
            print(f"::notice::published to {', '.join(ok)}")
            for f in failed:
                warn(f"{f} did not publish - see Upload-Post dashboard")
            return _finish(args, request_id, platforms, "published", ok, failed)
        if done and failed and not ok:
            die("publish failed: " + "; ".join(failed) + f" - details: {summary}")

    warn(f"no confirmation after {POLL_TIMEOUT}s. The upload may still complete; "
         f"check request_id {request_id} in the Upload-Post dashboard before re-running.")
    return _finish(args, request_id, platforms, "unconfirmed")


def _interpret(results, platforms: list[str]) -> tuple[list[str], list[str], bool]:
    """Return (succeeded, failed, finished) platform names."""
    if not isinstance(results, (dict, list)):
        return [], [], False
    items = results.items() if isinstance(results, dict) else [
        (e.get("platform", "unknown"), e) for e in results if isinstance(e, dict)
    ]
    ok, failed = [], []
    for name, entry in items:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status", "")).lower()
        success = entry.get("success")
        if success is True or status in {"completed", "published", "success", "done"}:
            ok.append(name)
        elif success is False or status in {"failed", "error", "rejected"}:
            # YouTube uploads from a project without audit fail with a privacy
            # error; surface that rather than a generic failure.
            reason = entry.get("error") or entry.get("message") or status
            failed.append(f"{name} ({reason})")
    finished = bool(ok or failed)
    return ok, failed, finished


def _finish(args, request_id, platforms, state, ok=None, failed=None) -> int:
    rep = Path(args.report)
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text(json.dumps({
        "provider": "upload-post",
        "request_id": request_id,
        "platforms": platforms,
        "state": state,
        "succeeded": ok or [],
        "failed": failed or [],
    }, indent=2), encoding="utf-8")
    print(f"wrote {rep}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
