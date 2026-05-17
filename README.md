# cono.rs

Plays a random video from the YouTube channel [@ConorNeill](https://www.youtube.com/@ConorNeill). Plain HTML + CSS + a tiny vanilla-JS picker, hosted on GitHub Pages at https://cono.rs.

## How it works

- [index.html](index.html) loads [videos.json](videos.json), picks a random entry, and embeds the YouTube player. A button re-rolls.
- [.github/workflows/refresh-videos.yml](.github/workflows/refresh-videos.yml) runs daily (and on demand). It calls the YouTube Data API via [scripts/refresh-videos.py](scripts/refresh-videos.py), regenerates `videos.json`, and commits the change if anything moved.

The whole site is still static — no server, no API calls from the browser.

## One-time setup

1. **Push this repo to GitHub** (e.g. `github.com/<you>/cono.rs`).
2. **Create a YouTube Data API v3 key**
   - Google Cloud Console → new project → APIs & Services → Enable *YouTube Data API v3* → Credentials → *Create credentials → API key*.
   - Optionally restrict the key to the YouTube Data API.
3. **Add the key as a repo secret**: GitHub → **Settings → Secrets and variables → Actions → New repository secret**, name `YOUTUBE_API_KEY`, paste the key.
4. **Run the workflow once** to populate `videos.json`: GitHub → **Actions → Refresh videos.json → Run workflow**. After it finishes, `videos.json` will be committed to `main`.
5. **Enable GitHub Pages**: **Settings → Pages → Build and deployment → Source: Deploy from a branch**, branch `main`, folder `/ (root)`.
6. **Point DNS for cono.rs** at GitHub Pages (the [CNAME](CNAME) file is already set):
   - Apex (`cono.rs`) — four `A` records:
     ```
     185.199.108.153
     185.199.109.153
     185.199.110.153
     185.199.111.153
     ```
   - `www.cono.rs` — `CNAME` to `<your-github-username>.github.io`.
7. Back in **Settings → Pages**, wait for the custom domain to verify, then tick **Enforce HTTPS**.

Every push to `main` redeploys. The scheduled workflow keeps `videos.json` fresh.

## Running the refresh locally

```sh
export YOUTUBE_API_KEY=...
python scripts/refresh-videos.py
```

Writes `videos.json` in the repo root.

## Changing the channel

Edit `YT_HANDLE` in [.github/workflows/refresh-videos.yml](.github/workflows/refresh-videos.yml) and the footer link in [index.html](index.html).
