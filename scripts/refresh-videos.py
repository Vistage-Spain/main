#!/usr/bin/env python3
"""Refresh videos.json with the full upload list from a YouTube channel.

For each video, also generate three social-share variants (X, LinkedIn,
Facebook) via the Anthropic API. Generation is cached by video ID: a
share block in the existing videos.json is reused, so the daily run only
spends API calls on genuinely new uploads.

Reads:
  YOUTUBE_API_KEY   – required, YouTube Data API v3 key
  YT_HANDLE         – channel @handle, e.g. @ConorNeill (default)
  ANTHROPIC_API_KEY – optional. If unset, share generation is skipped
                      and existing share blocks are preserved.
  ANTHROPIC_MODEL   – optional, defaults to claude-haiku-4-5
                      (cheapest model; try claude-sonnet-4-6 or
                      claude-opus-4-8 for higher-quality copy).

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
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")
OUTPUT = "videos.json"

if not API_KEY:
    sys.exit("YOUTUBE_API_KEY env var is required")


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


# ---------------------------------------------------------------------------
# YouTube Data API
# ---------------------------------------------------------------------------


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


def fetch_video_descriptions(video_ids: list[str]) -> dict[str, str]:
    """Map video_id -> description. Batches by 50 (the API limit)."""
    out: dict[str, str] = {}
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i : i + 50]
        params = urllib.parse.urlencode(
            {
                "part": "snippet",
                "id": ",".join(chunk),
                "key": API_KEY,
            }
        )
        data = _get(f"https://youtube.googleapis.com/youtube/v3/videos?{params}")
        for item in data.get("items", []):
            sn = item.get("snippet", {})
            out[item["id"]] = sn.get("description", "")
    return out


# ---------------------------------------------------------------------------
# Share-copy generation (Anthropic)
# ---------------------------------------------------------------------------

SHARE_SYSTEM_PROMPT = """\
You write social-media share copy for YouTube videos from Conor Neill —
a leadership coach, communication expert, and entrepreneur. The audience
is professionals: leaders, founders, executives, students of leadership.

For each video, produce three share variants:

- **x**: A hook-led post for X (Twitter). At most ~240 characters.
  Open with a strong claim, a question, or a counterintuitive observation.
  No hashtags. No emoji. One or two sentences max.

- **linkedin**: A professional post for LinkedIn. 2 to 4 short paragraphs,
  separated by blank lines. Lead with an insight or question that names the
  problem the video addresses. End with a soft pointer ("Worth a watch.",
  "Recommended viewing.", "Linked below."). At most ~1200 characters.
  No hashtags. No emoji.

- **facebook**: A conversational caption for Facebook. 1 to 3 sentences.
  Direct, warm, inviting — slightly less formal than the LinkedIn variant.
  At most ~400 characters. No hashtags.

Style rules across all three:
- Confident, professional, hook-led. Sound like an editor, not a marketer.
- Write in the third person ("In this video, Conor explores...",
  "Conor argues that...", "Conor unpacks..."). Never first person.
- Avoid empty superlatives: no "game-changing", "must-watch", "amazing",
  "incredible", "powerful insights", "deep dive", "you won't believe".
- Avoid clickbait framing ("This one thing...", "The secret to...").
- Be specific to the video's actual content. If the description is thin,
  stay general rather than inventing details.

Return STRICT JSON matching this schema and nothing else:
{"x": "...", "linkedin": "...", "facebook": "..."}
"""


_SHARE_SCHEMA = {
    "type": "object",
    "properties": {
        "x": {"type": "string"},
        "linkedin": {"type": "string"},
        "facebook": {"type": "string"},
    },
    "required": ["x", "linkedin", "facebook"],
    "additionalProperties": False,
}


def generate_share(client, title: str, description: str) -> dict[str, str]:
    """Ask Claude for the three share variants. Returns {x, linkedin, facebook}."""
    # Keep the description reasonable; YouTube descriptions can be huge
    # (timestamps, link dumps, sponsor blurbs).
    desc = (description or "").strip()
    if len(desc) > 3000:
        desc = desc[:3000] + "\n[...truncated]"

    user_content = (
        f"Video title: {title}\n\n"
        f"Video description:\n{desc or '(no description)'}"
    )

    # cache_control on the system prompt is a no-op while the prompt sits
    # below the model's minimum cacheable prefix (4096 tokens for Haiku 4.5);
    # leaving it on means caching kicks in automatically if the prompt grows
    # past that threshold (e.g. with added few-shot examples).
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": SHARE_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        output_config={
            "format": {
                "type": "json_schema",
                "schema": _SHARE_SCHEMA,
            }
        },
        messages=[{"role": "user", "content": user_content}],
    )

    text = next((b.text for b in response.content if b.type == "text"), "")
    if not text:
        raise RuntimeError("Claude returned no text block")
    return json.loads(text)


def load_existing_share_blocks() -> dict[str, dict]:
    """Map video_id -> share block from the existing videos.json (if any)."""
    try:
        with open(OUTPUT, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return {
        v["id"]: v["share"]
        for v in data.get("videos", [])
        if isinstance(v, dict) and v.get("id") and v.get("share")
    }


def populate_share_blocks(videos: list[dict]) -> tuple[int, int, int]:
    """Fill `share` on each video. Returns (reused, generated, failed)."""
    existing = load_existing_share_blocks()
    reused = generated = failed = 0

    # Apply cached blocks first
    for v in videos:
        cached = existing.get(v["id"])
        if cached:
            v["share"] = cached
            reused += 1

    # Decide whether to generate the rest
    missing = [v for v in videos if "share" not in v]
    if not missing:
        return reused, 0, 0
    if not ANTHROPIC_KEY:
        print(
            f"ANTHROPIC_API_KEY not set; leaving {len(missing)} videos without share copy.",
            file=sys.stderr,
        )
        return reused, 0, 0

    # Lazy import so the script still runs end-to-end when anthropic isn't installed
    import anthropic  # noqa: WPS433

    client = anthropic.Anthropic()
    print(
        f"Generating share copy for {len(missing)} new videos "
        f"(model={MODEL}, reused={reused})...",
        file=sys.stderr,
    )
    descriptions = fetch_video_descriptions([v["id"] for v in missing])
    for v in missing:
        try:
            v["share"] = generate_share(
                client, v["title"], descriptions.get(v["id"], "")
            )
            generated += 1
        except (anthropic.APIError, json.JSONDecodeError, RuntimeError) as exc:
            print(f"  share generation failed for {v['id']}: {exc}", file=sys.stderr)
            failed += 1

    return reused, generated, failed


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    channel_id, channel_title, uploads = resolve_channel(HANDLE)
    videos = list_uploads(uploads)
    # Newest first for stable diffs
    videos.sort(key=lambda v: v.get("publishedAt") or "", reverse=True)

    reused, generated, failed = populate_share_blocks(videos)

    with_share = sum(1 for v in videos if v.get("share"))
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

    summary = (
        f"Wrote {OUTPUT} with {len(videos)} videos from {channel_title} "
        f"({with_share} with share copy: reused={reused}, generated={generated}"
    )
    if failed:
        summary += f", failed={failed}"
    summary += ")"
    print(summary)


if __name__ == "__main__":
    main()
