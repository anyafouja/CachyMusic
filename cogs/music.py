import asyncio
import os
import discord
import random
import itertools
from discord.ext import commands
import wavelink
from supabase import create_client, Client

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')


class MusicPlayer:
    __slots__ = (
        'bot', '_guild', '_channel', '_cog',
        'queue', 'current', 'np', 'volume',
        'loop', '_stop', '_next_up', 'history',
        '_task',
    )

    def __init__(self, ctx):
        self.bot = ctx.bot
        self._guild = ctx.guild
        self._channel = ctx.channel
        self._cog = ctx.cog

        self.queue = asyncio.Queue()
        self.np = None
        self.volume = 0.5
        self.current = None
        self.loop = False
        self._stop = False
        self._next_up = None
        self.history = []

        self._task = ctx.bot.loop.create_task(self.player_loop())
        self._status_task = self.bot.loop.create_task(self.update_supabase_status())

    async def update_supabase_status(self):
        if not self._cog.supabase:
            return

        while not self.bot.is_closed() and not self._stop:
            try:
                vc = self._guild.voice_client
                status = {
                    'guild_id': str(self._guild.id),
                    'is_playing': vc.playing if vc else False,
                    'is_paused': vc.paused if vc else False,
                    'current_track': {
                        'title': self.current.title,
                        'author': self.current.author,
                        'length': self.current.length,
                        'artwork': self.current.artwork,
                        'uri': self.current.uri
                    } if self.current else None,
                    'queue': [
                        {'title': t.title, 'author': t.author, 'uri': t.uri}
                        for t in list(itertools.islice(self.queue._queue, 0, 10))
                    ],
                    'loop': self.loop,
                    'volume': int(self.volume * 100),
                    'updated_at': 'now()'
                }
                self._cog.supabase.table('bot_status').upsert(status).execute()
            except Exception:
                pass
            await asyncio.sleep(5)

    async def player_loop(self):
        await self.bot.wait_until_ready()

        try:
            while not self.bot.is_closed():
                self._stop = False

                try:
                    if self._next_up:
                        item = self._next_up
                        self._next_up = None
                    elif self.loop and self.current:
                        item = self.current
                    else:
                        item = await asyncio.wait_for(self.queue.get(), timeout=300)
                except asyncio.TimeoutError:
                    return
                except asyncio.CancelledError:
                    return

                track = item
                vc = self._guild.voice_client
                if not vc or not isinstance(vc, wavelink.Player):
                    return

                try:
                    await vc.play(track)
                except Exception:
                    self.current = None
                    continue

                self.current = track
                view = NowPlayingView(self, self._guild.id)

                try:
                    embed = discord.Embed(title=track.title[:256], color=0xFFC0CB)
                    if track.artwork:
                        embed.set_thumbnail(url=track.artwork)
                    embed.add_field(name='Saluran', value=track.author or 'Tidak diketahui')
                    embed.add_field(name='Durasi', value=_format_duration(track.length))
                    if self.np:
                        try:
                            await self.np.delete()
                        except Exception:
                            pass
                    self.np = await self._channel.send(embed=embed, view=view)
                except Exception:
                    pass

                try:
                    while vc.playing or vc.paused:
                        await asyncio.sleep(2)
                        if self._stop:
                            await vc.stop()
                            break
                        if not self._guild.voice_client:
                            return
                except Exception:
                    pass

                if not self._stop and self.current:
                    self.history.append(self.current)
                    if len(self.history) > 20:
                        self.history.pop(0)

                if not self.loop:
                    self.current = None

                if not self.current and self.queue.empty():
                    return
        except Exception:
            pass
        finally:
            await self._cog.cleanup(self._guild)


class NowPlayingView(discord.ui.View):
    def __init__(self, player, guild_id):
        super().__init__(timeout=None)
        self.player = player
        self.guild_id = guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id != self.guild_id:
            await interaction.response.send_message('Bukan untuk server ini.', ephemeral=True)
            return False
        vc = interaction.guild.voice_client
        if not vc or not vc.channel:
            await interaction.response.send_message('Tidak terhubung ke suara.', ephemeral=True)
            return False
        if interaction.user not in vc.channel.members:
            await interaction.response.send_message('Bergabunglah dengan saluran suara terlebih dahulu.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='\u25C1\u25C1', style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.player
        if not player.current:
            return await interaction.response.send_message('Tidak ada yang sedang diputar.', ephemeral=True)
        if not player.history:
            return await interaction.response.send_message('Tidak ada lagu sebelumnya.', ephemeral=True)
        player._next_up = player.history.pop()
        player._stop = True
        vc = interaction.guild.voice_client
        if vc:
            await vc.stop()
        await interaction.response.defer()

    @discord.ui.button(label='||', style=discord.ButtonStyle.secondary)
    async def pause_play(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if not vc or not isinstance(vc, wavelink.Player):
            return await interaction.response.send_message('Tidak terhubung.', ephemeral=True)
        if vc.paused:
            await vc.pause(False)
            button.label = '||'
        elif vc.playing:
            await vc.pause(True)
            button.label = '\u25B7'
        else:
            return await interaction.response.send_message('Tidak ada yang sedang diputar.', ephemeral=True)
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label='\u25B7\u25B7', style=discord.ButtonStyle.secondary)
    async def next_(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.player
        if not player.current:
            return await interaction.response.send_message('Tidak ada yang sedang diputar.', ephemeral=True)
        player._stop = True
        vc = interaction.guild.voice_client
        if vc:
            await vc.stop()
        await interaction.response.defer()

    @discord.ui.button(label='\u27F3', style=discord.ButtonStyle.secondary)
    async def loop_(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.player
        player.loop = not player.loop
        button.label = '\u27F2' if player.loop else '\u27F3'
        await interaction.response.edit_message(view=self)


def _format_duration(ms: int) -> str:
    seconds = ms // 1000
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f'{hours}h {minutes}m {sec}s'
    return f'{minutes}m {sec}s'


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}
        self.locks = {}
        self.supabase: Client = None
        if SUPABASE_URL and SUPABASE_KEY:
            self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            self.bot.loop.create_task(self.supabase_command_listener())

    async def supabase_command_listener(self):
        # Polling commands from supabase (since real-time python client is limited)
        while not self.bot.is_closed():
            try:
                res = self.supabase.table('bot_commands').select('*').eq('processed', False).order('created_at').execute()
                for cmd in res.data:
                    guild_id = int(cmd['guild_id'])
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        continue

                    action = cmd['action']
                    data = cmd.get('data', {})

                    # Mock a context for commands
                    # This is tricky because we need a channel to send messages
                    # We'll try to find a player first
                    player = self.players.get(guild_id)
                    if player:
                        ctx = await self.bot.get_context(player.np) if player.np else None # Not ideal

                        if action == 'play' and 'query' in data:
                            # Search and add to queue
                            tracks = await wavelink.Playable.search(data['query'])
                            if tracks:
                                track = tracks[0]
                                await player.queue.put(track)
                        elif action == 'previous':
                            if player.history:
                                player._next_up = player.history.pop()
                                player._stop = True
                                if guild.voice_client: await guild.voice_client.stop()
                        elif action == 'pause':
                            vc = guild.voice_client
                            if vc and vc.playing: await vc.pause(True)
                        elif action == 'resume':
                            vc = guild.voice_client
                            if vc and vc.paused: await vc.pause(False)
                        elif action == 'skip':
                            player._stop = True
                            if guild.voice_client: await guild.voice_client.stop()
                        elif action == 'stop':
                            await self.cleanup(guild)
                        elif action == 'volume':
                            vol = data.get('volume', 50)
                            vc = guild.voice_client
                            if vc: await vc.set_volume(vol)
                            player.volume = vol / 100

                    self.supabase.table('bot_commands').update({'processed': True}).eq('id', cmd['id']).execute()
            except Exception as e:
                print(f"Supabase error: {e}")
            await asyncio.sleep(2)

    async def cleanup(self, guild):
        try:
            player = self.players.get(guild.id)
            if player:
                player._stop = True
                if hasattr(player, '_status_task') and not player._status_task.done():
                    player._status_task.cancel()
                if player.np:
                    try:
                        await player.np.delete()
                    except Exception:
                        pass
                    player.np = None
                if player._task and not player._task.done():
                    player._task.cancel()
        except Exception:
            pass
        try:
            vc = guild.voice_client
            if vc:
                await vc.disconnect(force=True)
        except Exception:
            pass
        self.players.pop(guild.id, None)
        self.locks.pop(guild.id, None)

    async def get_player(self, ctx):
        guild_id = ctx.guild.id
        if guild_id not in self.locks:
            self.locks[guild_id] = asyncio.Lock()
        async with self.locks[guild_id]:
            if guild_id not in self.players:
                self.players[guild_id] = MusicPlayer(ctx)
            return self.players[guild_id]

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.id == self.bot.user.id:
            if after.channel is None:
                await self.cleanup(member.guild)
            return
        vc = member.guild.voice_client
        if vc and vc.channel and len([m for m in vc.channel.members if not m.bot]) == 0:
            await asyncio.sleep(10)
            vc = member.guild.voice_client
            if vc and vc.channel and len([m for m in vc.channel.members if not m.bot]) == 0:
                await self.cleanup(member.guild)

    async def _ensure_voice(self, ctx) -> bool:
        vc = ctx.voice_client

        if not ctx.author.voice:
            await ctx.send('Kamu tidak terhubung ke saluran suara.')
            return False

        target = ctx.author.voice.channel

        if not vc:
            if not await self.bot.ensure_node():
                await ctx.send('Node Lavalink tidak tersedia — coba lagi nanti.')
                return False
            try:
                vc = await target.connect(cls=wavelink.Player, reconnect=True)
            except Exception:
                # In case of "Already connected" or other issues, try to cleanup and reconnect
                await self.cleanup(ctx.guild)
                await asyncio.sleep(1)
                vc = await target.connect(cls=wavelink.Player, reconnect=True)
        elif vc.channel != target:
            await vc.move_to(target)

        return True

    async def _ensure_node(self, ctx) -> bool:
        if not await self.bot.ensure_node():
            await ctx.send('Node Lavalink tidak tersedia — coba lagi nanti.')
            return False
        return True

    @commands.hybrid_command(name='play', aliases=['p'])
    async def play_(self, ctx, *, search: str):
        """Plays a song from YouTube or SoundCloud."""
        await ctx.defer()
        if not await self._ensure_voice(ctx):
            return

        vc = ctx.voice_client

        try:
            tracks = await wavelink.Playable.search(
                search,
                source=wavelink.TrackSource.YouTube,
            )
            if not tracks:
                # Fallback to SoundCloud
                tracks = await wavelink.Playable.search(
                    search,
                    source=wavelink.TrackSource.SC,
                )
            if not tracks:
                return await ctx.send('Tidak ada hasil ditemukan.')

            track = tracks if isinstance(tracks, wavelink.Playlist) else tracks[0]

        except Exception as e:
            return await ctx.send(f'Pencarian gagal: `{e}`')

        player = await self.get_player(ctx)

        if isinstance(track, wavelink.Playlist):
            for t in track.tracks:
                await player.queue.put(t)
            embed = discord.Embed(title='Daftar Putar Ditambahkan', color=0xFFC0CB)
            embed.description = f'[{track.name}]({track.url}) — {len(track.tracks)} lagu'
            if track.artwork:
                embed.set_thumbnail(url=track.artwork)
        else:
            await player.queue.put(track)
            embed = discord.Embed(title='Ditambahkan ke Antrean', color=0xFFC0CB)
            embed.description = f'[{track.title}]({track.uri})'
            if track.artwork:
                embed.set_thumbnail(url=track.artwork)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='skip', aliases=['s'])
    async def skip_(self, ctx):
        """Skips the current song."""
        await ctx.defer()
        if not await self._ensure_node(ctx): return
        vc = ctx.voice_client
        if not vc or not (getattr(vc, 'playing', False) or getattr(vc, 'paused', False)):
            return await ctx.send('Tidak ada yang sedang diputar.')
        player = await self.get_player(ctx)
        player._stop = True
        await vc.stop()
        player.current = None
        await ctx.send(embed=discord.Embed(description='Lewati', color=0xFFC0CB))

    @commands.hybrid_command(name='stop')
    async def stop_(self, ctx):
        """Menghentikan musik dan memutuskan koneksi bot."""
        await ctx.defer()
        if not await self._ensure_node(ctx): return
        vc = ctx.voice_client
        if not vc or not vc.connected:
            return await ctx.send('Tidak terhubung.')
        await self.cleanup(ctx.guild)
        await ctx.send(embed=discord.Embed(description='Berhenti', color=0xFFC0CB))

    @commands.hybrid_command(name='pause')
    async def pause_(self, ctx):
        """Menjeda musik."""
        await ctx.defer()
        if not await self._ensure_node(ctx): return
        vc = ctx.voice_client
        if not vc or not isinstance(vc, wavelink.Player):
            return await ctx.send('Tidak terhubung ke Lavalink.')
        if vc.playing:
            await vc.pause(True)
            await ctx.send(embed=discord.Embed(description='Jeda', color=0xFFC0CB))
        else:
            await ctx.send('Tidak ada yang sedang diputar.')

    @commands.hybrid_command(name='resume')
    async def resume_(self, ctx):
        """Melanjutkan musik yang dijeda."""
        await ctx.defer()
        if not await self._ensure_node(ctx): return
        vc = ctx.voice_client
        if not vc or not isinstance(vc, wavelink.Player):
            return await ctx.send('Tidak terhubung.')
        if vc.paused:
            await vc.pause(False)
            await ctx.send(embed=discord.Embed(description='Dilanjutkan', color=0xFFC0CB))
        else:
            await ctx.send('Tidak sedang dijeda.')

    @commands.hybrid_command(name='queue', aliases=['q'])
    async def queue_info(self, ctx):
        """Menampilkan antrean lagu saat ini."""
        player = await self.get_player(ctx)
        if player.queue.empty():
            return await ctx.send('Antrean kosong.')
        upcoming = list(itertools.islice(player.queue._queue, 0, 10))
        fmt = '\n'.join(
            f"**{i+1}.** {item.title}" for i, item in enumerate(upcoming)
        )
        await ctx.send(embed=discord.Embed(title='Antrean', description=fmt, color=0xFFC0CB))

    @commands.hybrid_command(name='volume', aliases=['vol'])
    async def change_volume(self, ctx, vol: int):
        """Mengubah volume bot (1-100)."""
        await ctx.defer()
        if not await self._ensure_node(ctx): return
        vc = ctx.voice_client
        if not vc or not isinstance(vc, wavelink.Player):
            return await ctx.send('Tidak terhubung.')
        if not 0 < vol <= 100:
            return await ctx.send('Volume tidak valid (1-100).')
        await vc.set_volume(vol)
        player = await self.get_player(ctx)
        player.volume = vol / 100
        await ctx.send(embed=discord.Embed(description=f'Volume: {vol}%', color=0xFFC0CB))

    @commands.hybrid_command(name='nowplaying', aliases=['np'])
    async def nowplaying_(self, ctx):
        """Menampilkan trek yang sedang diputar."""
        vc = ctx.voice_client
        if not vc or not isinstance(vc, wavelink.Player) or not vc.playing:
            return await ctx.send('Tidak ada yang sedang diputar.')
        track = vc.current
        embed = discord.Embed(
            title=track.title[:256],
            url=track.uri,
            color=0xFFC0CB,
        )
        if track.artwork:
            embed.set_thumbnail(url=track.artwork)
        embed.add_field(name='Saluran', value=track.author or 'Tidak diketahui')
        embed.add_field(name='Durasi', value=_format_duration(track.length))
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='help')
    async def help_(self, ctx):
        """Menampilkan semua perintah."""
        cmds = [
            ('play <kueri>', 'Cari & putar dari YouTube / SoundCloud melalui Lavalink'),
            ('skip', 'Melewati lagu saat ini'),
            ('stop', 'Menghentikan pemutaran dan memutuskan koneksi'),
            ('pause', 'Menjeda pemutaran'),
            ('resume', 'Melanjutkan pemutaran'),
            ('volume <1-100>', 'Mengatur volume'),
            ('queue', 'Menampilkan antrean lagu'),
            ('nowplaying', 'Menampilkan info trek saat ini'),
            ('clear-queue', 'Menghapus semua lagu yang antre'),
            ('shuffle', 'Mengacak antrean'),
            ('loop', 'Beralih mode pengulangan'),
            ('ping', 'Memeriksa latensi bot'),
        ]
        embed = discord.Embed(title='Cachy Music', color=0xFFC0CB)
        embed.description = '\n\n'.join(f'**cachy {cmd}**\n{desc}' for cmd, desc in cmds)
        embed.set_footer(text='Didukung oleh Lavalink | YouTube + SoundCloud')
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='ping')
    async def ping_(self, ctx):
        """Memeriksa latensi bot."""
        await ctx.send(embed=discord.Embed(
            description=f'Pong! {round(self.bot.latency * 1000)}ms',
            color=0xFFC0CB,
        ))

    @commands.hybrid_command(name='clear-queue')
    async def clear_queue_(self, ctx):
        """Menghapus semua lagu dari antrean."""
        player = await self.get_player(ctx)
        while not player.queue.empty():
            try:
                player.queue.get_nowait()
            except Exception:
                break
        await ctx.send(embed=discord.Embed(description='Antrean dikosongkan', color=0xFFC0CB))

    @commands.hybrid_command(name='loop')
    async def loop_(self, ctx):
        """Beralih pengulangan lagu saat ini."""
        player = await self.get_player(ctx)
        player.loop = not player.loop
        await ctx.send(embed=discord.Embed(
            description=f'Pengulangan {"aktif" if player.loop else "nonaktif"}',
            color=0xFFC0CB,
        ))

    @commands.hybrid_command(name='shuffle')
    async def shuffle_(self, ctx):
        """Mengacak lagu-lagu di antrean."""
        player = await self.get_player(ctx)
        if player.queue.empty():
            return await ctx.send('Antrean kosong.')
        songs = []
        while not player.queue.empty():
            try:
                songs.append(player.queue.get_nowait())
            except Exception:
                break
        random.shuffle(songs)
        for song in songs:
            await player.queue.put(song)
        await ctx.send(embed=discord.Embed(description='Diacak', color=0xFFC0CB))


async def setup(bot):
    await bot.add_cog(Music(bot))
