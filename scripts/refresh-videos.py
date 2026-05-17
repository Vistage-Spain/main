#!/usr/bin/env python3
"""Refresh videos.json with the full upload list from a YouTube channel.

Reads:
  YOUTUBE_API_KEY  – required, YouTube Data API v3 key
  YT_HANDLE        – channel @handle, e.g. @ConorNeill (default)

Writes ./videos.json
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request


API_KEY = os.environ.get("YOUTUBE_API_KEY")
HANDLE = os.environ.get("YT_HANDLE", "@ConorNeill")
OUTPUT = "videos.json"

if not API_KEY:
    sys.exit("YOUTUBE_API_KEY env var is required")


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def resolve_channel(handle: str) -> tuple[str, str, str]:
    """Return (channel_id, channel_title, uploads_playlist_id)."""
    params = urllib.parse.urlencode(
        {
            "part": "snippet,contentDetails",
            "forHandle": handle,
            "key": API_KEY,
        }
    )
    data = _get(f"https://youtube.googleapis.com/youtube/v3/channels?{params}")
    items = data.get("items") or []
    if not items:
        sys.exit(f"No channel found for handle {handle!r}")
    ch = items[0]
    return (
        ch["id"],
        ch["snippet"]["title"],
        ch["contentDetails"]["relatedPlaylists"]["uploads"],
    )


def list_uploads(playlist_id: str) -> list[dict]:
    videos: list[dict] = []
    page_token: str | None = None
    while True:
        params: dict[str, str | int] = {
            "part": "snippet,contentDetails,status",
            "playlistId": playlist_id,
            "maxResults": 50,
            "key": API_KEY,
        }
        if page_token:
            params["pageToken"] = page_token
        data = _get(
            "https://youtube.googleapis.com/youtube/v3/playlistItems?"
            + urllib.parse.urlencode(params)
        )
        for item in data.get("items", []):
            sn = item.get("snippet", {})
            cd = item.get("contentDetails", {})
            status = (item.get("status") or {}).get("privacyStatus")
            title = sn.get("title") or ""
            # Skip private / deleted / unlisted
            if title in ("Private video", "Deleted video"):
                continue
            if status and status != "public":
                continue
            video_id = cd.get("videoId")
            if not video_id:
                continue
            videos.append(
                {
                    "id": video_id,
                    "title": title,
                    "publishedAt": cd.get("videoPublishedAt")
                    or sn.get("publishedAt"),
                }
            )
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return videos


def main() -> None:
    channel_id, channel_title, uploads = resolve_channel(HANDLE)
    videos = list_uploads(uploads)
    # Sort newest first for stable diffs
    videos.sort(key=lambda v: v.get("publishedAt") or "", reverse=True)
    payload = {
        "channel": {
            "id": channel_id,
            "title": channel_title,
            "handle": HANDLE,
        },
        "updatedAt": dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "count": len(videos),
        "videos": videos,
    }
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {OUTPUT} with {len(videos)} videos from {channel_title}")


if __name__ == "__main__":
    main()
