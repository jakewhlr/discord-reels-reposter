# Discord Reels Reposter

A Discord bot that automatically downloads and re-embeds Instagram Reels and TikTok videos as native Discord videos, making them viewable without login.

## Features

- Supports Instagram Reels/Posts and TikTok videos
- Automatic video compression for files exceeding Discord's size limits
- Handles multiple URLs in a single message
- Visual feedback with emoji reactions (⏬ downloading, 🔄 compressing, ✅ success, ❌ error)

## How It Works

1. Detects Instagram or TikTok URLs in Discord messages
2. Downloads the video using yt-dlp
3. Compresses if needed to fit Discord's 8MB limit
4. Re-uploads as a native Discord video
5. Cleans up temporary files

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
- Python 3.9+
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

### Discord Bot Setup

1. Create a bot at [Discord Developer Portal](https://discord.com/developers/applications)
2. Enable **Message Content Intent** under Bot settings
3. Invite bot with these permissions:
   - Read Messages/View Channels
   - Send Messages
   - Attach Files
   - Add Reactions

## Usage

Post Instagram or TikTok URLs in any channel:

```
https://www.instagram.com/reel/abc123/
https://www.tiktok.com/@user/video/1234567890
https://vm.tiktok.com/xyz/
```

The bot will automatically download and re-upload the video.

## Configuration

Edit `config.py`:

- `MAX_FILE_SIZE` - Size limit (default: 8MB, increase for boosted servers)
- `ENABLE_COMPRESSION` - Auto-compress oversized videos (default: True)
- `MAX_COMPRESSION_ATTEMPTS` - Compression retries (default: 3)

## Troubleshooting

**Bot doesn't respond:**
- Enable Message Content Intent in Discord Developer Portal
- Check logs: `docker-compose logs -f` or console output

**Videos too large:**
- Compression is enabled by default
- Increase `MAX_FILE_SIZE` for boosted servers (50MB or 500MB)

**Download fails:**
- Video may be private or deleted
- Platform may be rate-limiting requests

---

## Credits

Created with [OpenCode](https://opencode.ai) + Claude Sonnet 4.5

