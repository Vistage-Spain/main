# vids.cono.rs

Plays a random video from the YouTube channel [@ConorNeill](https://www.youtube.com/@ConorNeill). Plain HTML + CSS + a tiny vanilla-JS picker, hosted on GitHub Pages at https://vids.cono.rs.

## How it works

- [index.html](index.html) loads [videos.json](videos.json), picks a random entry, and embeds the YouTube player. A button re-rolls. Share buttons (X / LinkedIn / Facebook) use platform-tuned copy from each video's `share` block when present, falling back to the raw title.
- [.github/workflows/refresh-videos.yml](.github/workflows/refresh-videos.yml) runs daily (and on demand). It calls the YouTube Data API via [scripts/refresh-videos.py](scripts/refresh-videos.py), generates share copy for any new uploads via Claude (cached by video ID — existing copy is preserved), regenerates `videos.json`, and commits the change if anything moved.

The whole site is still static — no server, no API calls from the browser.

## One-time setup

1. **Push this repo to GitHub** (e.g. `github.com/<you>/cono.rs`).
2. **Create a YouTube Data API v3 key**
   - Google Cloud Console → new project → APIs & Services → Enable *YouTube Data API v3* → Credentials → *Create credentials → API key*.
   - Optionally restrict the key to the YouTube Data API.
3. **Add the key as a repo secret**: GitHub → **Settings → Secrets and variables → Actions → New repository secret**, name `YOUTUBE_API_KEY`, paste the key.
4. **(Optional) Add an Anthropic API key** for AI-generated share copy: same place, secret name `ANTHROPIC_API_KEY`. Get a key from [console.anthropic.com](https://console.anthropic.com/) → API Keys. Without this secret, share buttons fall back to the raw video title. Default model is `claude-haiku-4-5` (~$0.002/video); override by uncommenting `ANTHROPIC_MODEL` in the workflow if you want Sonnet or Opus quality.
5. **Run the workflow once** to populate `videos.json`: GitHub → **Actions → Refresh videos.json → Run workflow**. After it finishes, `videos.json` will be committed to `main`. The first run does a one-time backfill of share copy for every existing upload (cost: roughly $0.40 on Haiku 4.5 for a 200-video channel); subsequent runs only generate copy for genuinely new videos.
6. **Enable GitHub Pages**: **Settings → Pages → Build and deployment → Source: Deploy from a branch**, branch `main`, folder `/ (root)`.
7. **Point DNS for `vids.cono.rs`** at GitHub Pages (the [CNAME](CNAME) file is already set to `vids.cono.rs`):
   - At your DNS host for `cono.rs`, add one `CNAME` record:
     - **Name / host**: `vids`
     - **Value / target**: `<your-github-username>.github.io.` (note the trailing dot if your host requires it)
     - **TTL**: default is fine
8. Back in **Settings → Pages**, wait for the custom domain to verify, then tick **Enforce HTTPS**.

Every push to `main` redeploys. The scheduled workflow keeps `videos.json` fresh.

## Running the refresh locally

```sh
export YOUTUBE_API_KEY=...
export ANTHROPIC_API_KEY=...           # optional, enables share-copy generation
# export ANTHROPIC_MODEL=claude-sonnet-4-6  # optional, defaults to claude-haiku-4-5
pip install anthropic                  # only needed if ANTHROPIC_API_KEY is set
python scripts/refresh-videos.py
```

Writes `videos.json` in the repo root. Share copy is cached by video ID — only new uploads trigger new API calls.

## Changing the channel

Edit `YT_HANDLE` in [.github/workflows/refresh-videos.yml](.github/workflows/refresh-videos.yml) and the footer link in [index.html](index.html).
