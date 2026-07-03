-- Tabel untuk status bot (Sync Bot -> Dashboard)
CREATE TABLE bot_status (
    guild_id TEXT PRIMARY KEY,
    is_playing BOOLEAN DEFAULT FALSE,
    is_paused BOOLEAN DEFAULT FALSE,
    current_track JSONB,
    queue JSONB DEFAULT '[]'::jsonb,
    loop BOOLEAN DEFAULT FALSE,
    volume INTEGER DEFAULT 50,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabel untuk perintah (Sync Dashboard -> Bot)
CREATE TABLE bot_commands (
    id BIGSERIAL PRIMARY KEY,
    guild_id TEXT NOT NULL,
    action TEXT NOT NULL,
    data JSONB DEFAULT '{}'::jsonb,
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Aktifkan Realtime untuk tabel bot_status
ALTER PUBLICATION supabase_realtime ADD TABLE bot_status;
