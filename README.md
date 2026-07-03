# Cachy Music

Discord music bot powered by **Lavalink** — no YouTube blocking, no cookies needed. Lengkap dengan Dashboard Kontrol.

## Fitur Baru: Dashboard Kontrol
Bot ini sekarang dilengkapi dengan Dashboard berbasis Next.js yang dideploy ke Vercel untuk mengontrol musik secara visual.

### Persiapan Supabase
1. Buat proyek baru di [Supabase](https://supabase.com).
2. Jalankan perintah SQL yang ada di file `supabase_schema.sql` di SQL Editor Supabase.
3. Dapatkan `SUPABASE_URL` dan `SUPABASE_KEY` dari Settings -> API.

### Environment Variables
#### Untuk Bot (GitHub Secrets):
- `DISCORD_TOKEN`: Token bot Discord Anda.
- `LAVALINK_URI`: URI Node Lavalink.
- `LAVALINK_PASSWORD`: Password Node Lavalink.
- `SUPABASE_URL`: URL proyek Supabase Anda.
- `SUPABASE_KEY`: Service Role Key Supabase (untuk akses tulis).

#### Untuk Dashboard (Vercel):
- `NEXT_PUBLIC_SUPABASE_URL`: URL proyek Supabase Anda.
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`: Anon Key Supabase.
- `DISCORD_CLIENT_ID`: Client ID aplikasi Discord Anda.
- `DISCORD_CLIENT_SECRET`: Client Secret aplikasi Discord Anda.
- `OWNER_ID`: ID Discord Anda (hanya Anda yang bisa login).


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

Default Lavalink node: `lavalink.jirayu.net:13592` (password: `youshallnotpass`). Override via `LAVALINK_URI` / `LAVALINK_PASSWORD` env vars.

### GitHub Actions

Add secrets:
- `DISCORD_TOKEN` — your bot token
