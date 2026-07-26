# Cachy Music

Discord music bot powered by **Lavalink** — no YouTube blocking, no cookies needed.

YouTube & SoundCloud via Lavalink public nodes (wavelink). Runs locally or on GitHub Actions.

## Commands

| Command | Description |
|---------|-------------|
| `cachy play <query>` | Play from YouTube or SoundCloud |
| `cachy skip` | Skip current track |
| `cachy stop` | Stop and disconnect |
| `cachy pause / resume` | Pause/resume playback |
| `cachy queue` | Show the queue |
| `cachy volume <1-100>` | Set volume |
| `cachy nowplaying` | Show current track info |
| `cachy loop` | Toggle loop |
| `cachy shuffle` | Shuffle the queue |
| `cachy clear-queue` | Clear all queued tracks |
| `cachy ping` | Check latency |

## Setup

1. Clone repo
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env`, fill `DISCORD_TOKEN`
4. `python main.py`

Default Lavalink node: `lavalink-v4.triniumhost.com:443` (password: `free`). Override via `LAVALINK_URI` / `LAVALINK_PASSWORD` env vars.

### GitHub Actions

Add secrets:
- `DISCORD_TOKEN` — your bot token
