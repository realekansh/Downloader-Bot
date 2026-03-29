
# HyperTech Downloader Bot

HyperTech Downloader Bot is a Telegram bot for downloading media from supported public links in private chats and approved groups. It supports a simple local dev mode, a Redis-backed worker queue for production, and admin controls for group approval and rank-based limits.

## Features

- Download media from supported public links with yt-dlp
- Work in private chats and approved Telegram groups
- Support auto-download when links are posted
- Use hidden admin commands for approvals and moderation
- Enforce group rank limits for cooldowns, file size, and concurrency
- Run in DEV_MODE with SQLite and in-process downloads
- Run in production with PostgreSQL, Redis, and RQ workers
- Show cleaner Telegram UI messages and cleaner console logs

## Supported Platforms

- YouTube
- Instagram
- TikTok
- Facebook
- X/Twitter

Platform support ultimately depends on what yt-dlp can extract from the public link you send.

## Commands

### Public Commands

- /start - Start the bot
- /help - View the help menu
- /download <url> - Download media from a supported link
- /info - View your profile or group statistics
- /autodl - Toggle auto-download

### Hidden Admin Commands

- /adminhelp - Show admin-only help
- /promote <user_id|@username|reply> - Promote a user to admin
- /demote <user_id|@username|reply> - Remove admin access
- /addgroup - Approve the current group
- /rmgroup - Remove group approval
- /setrank <full|sudo|less> - Set the current group rank

### Group Ranks

- Full - No restrictions
- Sudo - 100 MB limit and 10 second cooldown
- Less - 50 MB limit and 30 second cooldown

## Project Structure

- `main.py` - bot entry point
- `handlers/` - Telegram command and message handlers
- `middlewares/` - auth, logging, and rate-limit middleware
- `workers/` - background download worker
- `utils/` - downloader, formatting, permissions, and Redis helpers
- `database/` - models and DB connection/bootstrap logic
- `alembic/` - production migrations

## Environment Variables

Use `.env.example` as the base for your local `.env`.

Required:

- `BOT_TOKEN` - Telegram bot token from BotFather
- `OWNER_ID` - Telegram user ID for the bot owner
- `DATABASE_URL` - SQLAlchemy database URL

Common options:

- `REDIS_HOST`
- `REDIS_PORT`
- `REDIS_DB`
- `REDIS_PASSWORD`
- `DOWNLOAD_PATH`
- `DOWNLOAD_JOB_TIMEOUT`
- `DEV_MODE`
- `DEBUG`

Docker convenience variables:

- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`

## Local Development

This is the easiest way to run the bot on one machine without Docker.

### 1. Create and activate a virtual environment

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
