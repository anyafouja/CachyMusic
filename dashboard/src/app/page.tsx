"use client";

import { useState, useEffect } from 'react';
import { supabase } from '@/lib/supabase';
import { Play, Pause, SkipForward, SkipBack, Volume2 } from 'lucide-react';

export default function Dashboard() {
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStatus = async () => {
      const { data } = await supabase
        .from('bot_status')
        .select('*')
        .single();
      setStatus(data);
      setLoading(false);
    };

    fetchStatus();

    const subscription = supabase
      .channel('bot_status')
      .on('postgres_changes', { event: 'UPDATE', schema: 'public', table: 'bot_status' }, (payload) => {
        setStatus(payload.new);
      })
      .subscribe();

    return () => {
      supabase.removeChannel(subscription);
    };
  }, []);

  const sendCommand = async (action: string, data = {}) => {
    if (!status?.guild_id) return;
    await supabase.from('bot_commands').insert({
      guild_id: status.guild_id,
      action,
      data,
      processed: false
    });
  };

  if (loading) return <div className="flex items-center justify-center min-h-screen">Memuat...</div>;

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <h1 className="text-3xl font-bold mb-8">Cachy Music Dashboard</h1>

      <div className="bg-white shadow rounded-lg p-6 mb-8 border border-pink-200">
        <h2 className="text-xl font-semibold mb-4 text-pink-600">Sedang Diputar</h2>
        {status?.current_track ? (
          <div className="flex items-center gap-6">
            {status.current_track.artwork && (
              <img src={status.current_track.artwork} alt="Artwork" className="w-32 h-32 rounded-lg object-cover shadow" />
            )}
            <div>
              <p className="text-lg font-medium">{status.current_track.title}</p>
              <p className="text-gray-500">{status.current_track.author}</p>
            </div>
          </div>
        ) : (
          <p className="text-gray-400 italic">Tidak ada lagu yang diputar</p>
        )}
      </div>

      <div className="flex gap-4 justify-center mb-8">
        <button onClick={() => sendCommand('previous')} className="p-4 bg-gray-100 hover:bg-gray-200 rounded-full transition shadow-sm">
          <SkipBack size={24} />
        </button>
        <button
          onClick={() => sendCommand(status?.is_playing ? 'pause' : 'resume')}
          className="p-4 bg-pink-500 hover:bg-pink-600 text-white rounded-full transition shadow-lg"
        >
          {status?.is_playing ? <Pause size={24} /> : <Play size={24} />}
        </button>
        <button onClick={() => sendCommand('skip')} className="p-4 bg-gray-100 hover:bg-gray-200 rounded-full transition shadow-sm">
          <SkipForward size={24} />
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <div className="bg-white shadow rounded-lg p-6 border border-pink-100">
          <h2 className="text-xl font-semibold mb-4 text-pink-600">Antrean</h2>
          <div className="space-y-3">
            {status?.queue?.map((item: any, i: number) => (
              <div key={i} className="flex justify-between items-center text-sm border-b pb-2 last:border-0">
                <span className="truncate flex-1 pr-4">{i + 1}. {item.title}</span>
                <span className="text-gray-400 text-xs shrink-0">{item.author}</span>
              </div>
            )) || <p className="text-gray-400 italic text-sm">Antrean kosong</p>}
          </div>
        </div>

        <div className="bg-white shadow rounded-lg p-6 border border-pink-100">
          <h2 className="text-xl font-semibold mb-4 text-pink-600">Pengaturan</h2>
          <div className="flex items-center gap-4">
            <Volume2 size={20} className="text-gray-500" />
            <input
              type="range"
              min="1" max="100"
              value={status?.volume || 50}
              onChange={(e) => sendCommand('volume', { volume: parseInt(e.target.value) })}
              className="w-full accent-pink-500"
            />
            <span className="text-sm font-medium w-8">{status?.volume}%</span>
          </div>
        </div>
      </div>
    </div>
  );
}
