# Discord Reels Reposter

A Discord bot that automatically downloads and re-embeds short videos from social platforms as native Discord videos, making them viewable without a login.

## Features

- Supports **Instagram** Reels/Posts, **Facebook** Reels/Videos, **X** (Twitter), **YouTube Shorts**, **TikTok**, and **Reddit** (cookies required)
- Rewrites embed-fixer mirror links (`vxtwitter.com`, `ddinstagram.com`, …) back to the canonical host
- Rich embeds carrying the caption, author, engagement stats and original post time
- Automatic video compression for files exceeding Discord's size limits
- Handles multiple URLs in a single message, de-duplicated
- Skips videos longer than `MAX_DURATION_SECONDS` instead of trying to squeeze them into 8MB
- Visual feedback with emoji reactions (⏬ downloading, 🔄 compressing, ✅ success, 🔒 login required, ❌ error)

### Platform status

Extractors for these sites break often; this is the state as last verified:

| Platform | Works anonymously | Notes |
|---|---|---|
| Facebook | ✅ | Reels, watch pages, `fb.watch`, `/share/v/` links |
| X (Twitter) | ✅ | Needs cookies for age-restricted posts |
| YouTube Shorts | ✅ | Shorts only — full-length links are deliberately ignored |
| Instagram | ✅ | **Requires curl-cffi and a recent yt-dlp**; older versions return "login required" |
| Reddit | ❌ | Serves a "prove your humanity" challenge to anonymous requests. Disabled until a cookie source is configured |
| TikTok | ❌ | Currently failing (`Unexpected response from webpage request`) — needs a follow-up |

Keeping `yt-dlp` current matters more than usual here. The Docker image installs the
nightly (`--pre`), which is why it can fetch Instagram when a year-old stable release cannot.

## How It Works

1. Detects supported URLs in Discord messages
2. Probes the video's duration, skipping anything over the limit
3. Downloads with yt-dlp, muxing separate video+audio streams when the platform serves DASH only
4. Compresses if needed to fit Discord's 8MB limit
5. Replies with a rich embed plus the video as a native attachment
6. Cleans up temporary files

## Quick Start (Docker)

```bash
# 1. Configure your bot token
cp .env.example .env
# Edit .env and add your Discord bot token

# 2. Start the bot
docker-compose up -d

# 3. View logs
docker-compose logs -f
```

## Local Development

### Prerequisites
- Python 3.10+
- [uv](https://github.com/astral-sh/uv)
- FFmpeg (`brew install ffmpeg` on macOS, `apt install ffmpeg` on Ubuntu)

### Setup

```bash
# Install dependencies
uv sync

# Configure bot token
# Edit .env and add your Discord token

# Run the bot
uv run python bot.py
```

### Tests

```bash
uv run --with pytest pytest -q
```

The embed and error-classification tests use metadata captured verbatim from live
URLs, so they reflect each platform's real quirks (Facebook's stats-polluted
titles, Instagram's `"Video by <handle>"` boilerplate, X's duplicated title).

### Discord Bot Setup

1. Create a bot at [Discord Developer Portal](https://discord.com/developers/applications)
2. Enable **Message Content Intent** under Bot settings
3. Invite bot with these permissions:
   - Read Messages/View Channels
   - Send Messages
   - Attach Files
   - Add Reactions
   - Embed Links

## Usage

Post a supported URL in any channel:

```
https://www.instagram.com/reel/abc123/
https://www.facebook.com/reel/1234567890
https://fb.watch/abc123/
https://x.com/user/status/1234567890
https://www.youtube.com/shorts/abc123
https://www.tiktok.com/@user/video/1234567890
```

The bot downloads it and replies with the video plus an embed.

Links that simply aren't videos (a Reddit text post, a tweet with no media) are
ignored silently rather than answered with an error — a share link gives no hint
about its contents, so the bot has to try before it can know.

## Configuration

Platform patterns, colours and download options live in `config.py`:

- `MAX_FILE_SIZE` — Size limit (default: 8MB, increase for boosted servers)
- `ENABLE_COMPRESSION` — Auto-compress oversized videos (default: True)
- `MAX_COMPRESSION_ATTEMPTS` — Compression retries (default: 3)
- `PLATFORM_PATTERNS` — URL patterns per platform; add a platform by adding an entry
- `PLATFORM_COLORS` — Embed accent colour per platform

Environment variables (`.env`):

| Variable | Default | Purpose |
|---|---|---|
| `DISCORD_BOT_TOKEN` | — | Required |
| `MAX_DURATION_SECONDS` | `900` | Skip videos longer than this; `0` disables |
| `ENABLE_EMBEDS` | `true` | Attach the caption/author/stats embed |
| `ENABLE_EMBED_THUMBNAIL` | `false` | Add the poster frame as an embed thumbnail (duplicates the attached video) |
| `EMBED_DESCRIPTION_LIMIT` | `400` | Caption truncation length |
| `YTDL_COOKIES_FILE` | — | Path to a `cookies.txt`; enables Reddit and login-gated posts |
| `YTDL_COOKIES_FROM_BROWSER` | — | Alternative: `firefox`, `chrome:Default`, … |

### Enabling Reddit

Reddit is ignored entirely until a cookie source is set, so that Reddit links
don't draw a failure reply every time. To turn it on, export cookies for
`reddit.com` in Netscape format, mount the file into the container, and set:

```yaml
# docker-compose.yml
    volumes:
      - ./cookies.txt:/app/cookies.txt:ro
    environment:
      - YTDL_COOKIES_FILE=/app/cookies.txt
```

Treat that file as a credential — it grants access to the account.

## Troubleshooting

**Bot doesn't respond:**
- Enable Message Content Intent in Discord Developer Portal
- Check logs: `docker-compose logs -f` or console output

**Videos too large:**
- Compression is enabled by default
- Increase `MAX_FILE_SIZE` for boosted servers (50MB or 500MB)

**Download fails / "login required":**
- Video may be private or deleted
- Rebuild to pick up a newer yt-dlp: `docker-compose build --no-cache && docker-compose up -d`
- Supply cookies via `YTDL_COOKIES_FILE` for login-gated posts

**Video has no audio:**
- The format chain merges separate audio/video streams and needs FFmpeg present in the image

---

## Credits

Created with [OpenCode](https://opencode.ai) + Claude Sonnet 4.5
