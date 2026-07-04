import asyncio
import discord
import random
import itertools
from discord.ext import commands
import wavelink


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
        self.volume = ctx.cog.volumes.get(ctx.guild.id, 100)
        self.current = None
        self.loop = False
        self._stop = False
        self._next_up = None
        self.history = []

        self._task = asyncio.create_task(self.player_loop())

    def create_embed(self, vc: wavelink.Player):
        track = self.current
        if not track:
            return None

        embed = discord.Embed(color=0x5865f2)
        embed.set_author(name="Now playing")

        requester_mention = "Tidak diketahui"
        if hasattr(track, 'requester'):
            requester_mention = track.requester.mention

        # Konten utama
        description = f"**[{track.title[:100]}]({track.uri})**\n"
        description += f"• Added by {requester_mention}\n"

        voice_channel = "Unknown"
        if vc.channel:
            voice_channel = vc.channel.name
        description += f"• 🔊 {voice_channel}\n\n"

        # Baris statistik
        queue_size = self.queue.qsize()
        loop_status = "On" if self.loop else "Off"
        description += f"Queue Size: `{queue_size}` · Volume: `{self.volume}%` · Loop: `{loop_status}`\n\n"

        # Progress Bar
        pos_ms = vc.position
        dur_ms = track.length
        bar_size = 25

        if dur_ms > 0:
            progress = min(pos_ms / dur_ms, 1.0)
            filled = int(progress * bar_size)
            bar = "━" * filled + "🔘" + "━" * (bar_size - filled)
        else:
            bar = "🔘" + "━" * bar_size

        pos_str = _format_duration(pos_ms)
        dur_str = _format_duration(dur_ms)

        description += f"{bar}\n`{pos_str}`" + (" " * 35) + f"`{dur_str}`"

        embed.description = description

        if track.artwork:
            embed.set_thumbnail(url=track.artwork)

        return embed

    async def player_loop(self):
        await self.bot.wait_until_ready()

        try:
            while not self.bot.is_closed():
                try:
                    if self._next_up:
                        item = self._next_up
                        self._next_up = None
                    elif self.loop and self.current:
                        item = self.current
                    else:
                        # Tunggu lagu baru atau timeout setelah 3 menit (180 detik) ketidakaktifan
                        item = await asyncio.wait_for(self.queue.get(), timeout=180)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    await self._cog.cleanup(self._guild)
                    return

                track = item
                vc = self._guild.voice_client
                if not vc or not isinstance(vc, wavelink.Player):
                    return

                self._stop = False
                self.current = track

                try:
                    await vc.play(track)
                except Exception:
                    self.current = None
                    continue

                view = NowPlayingView(self, self._guild.id)
                try:
                    embed = self.create_embed(vc)
                    if self.np:
                        try:
                            await self.np.delete()
                        except Exception:
                            pass
                    self.np = await self._channel.send(embed=embed, view=view)
                except Exception:
                    pass

                try:
                    count = 0
                    while (vc.playing or vc.paused) and self._guild.voice_client:
                        await asyncio.sleep(2)
                        count += 1

                        # Perbarui embed dan tombol setiap 10 detik (5 iterasi * 2 detik)
                        if count % 5 == 0 and self.np:
                            try:
                                view.update_buttons(vc)
                                embed = self.create_embed(vc)
                                await self.np.edit(embed=embed, view=view)
                            except Exception:
                                pass

                        if self._stop:
                            break

                    if self._stop:
                        await vc.stop()
                except Exception:
                    pass

                if not self._stop and self.current:
                    self.history.append(self.current)
                    if len(self.history) > 20:
                        self.history.pop(0)

                if not self.loop:
                    self.current = None

                # Langsung putus koneksi jika antrean kosong setelah lagu selesai
                if not self.loop and self.queue.empty() and not self._next_up:
                    await self._cog.cleanup(self._guild)
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

    @discord.ui.button(emoji='⏮️', style=discord.ButtonStyle.secondary)
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

    @discord.ui.button(emoji='⏸️', style=discord.ButtonStyle.secondary)
    async def pause_play(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if not vc or not isinstance(vc, wavelink.Player):
            return await interaction.response.send_message('Tidak terhubung.', ephemeral=True)
        if vc.paused:
            await vc.pause(False)
        elif vc.playing:
            await vc.pause(True)
        else:
            return await interaction.response.send_message('Tidak ada yang sedang diputar.', ephemeral=True)

        self.update_buttons(vc)
        embed = self.player.create_embed(vc)
        await interaction.response.edit_message(embed=embed, view=self)

    def update_buttons(self, vc: wavelink.Player):
        # Update Pause/Play button
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.emoji and str(child.emoji) in ['⏸️', '▶️']:
                    child.emoji = '▶️' if vc.paused else '⏸️'
                if child.emoji and str(child.emoji) == '🔁':
                    child.style = discord.ButtonStyle.primary if self.player.loop else discord.ButtonStyle.secondary

    @discord.ui.button(emoji='⏭️', style=discord.ButtonStyle.secondary)
    async def next_(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.player
        if not player.current:
            return await interaction.response.send_message('Tidak ada yang sedang diputar.', ephemeral=True)
        player._stop = True
        vc = interaction.guild.voice_client
        if vc:
            await vc.stop()
        await interaction.response.defer()

    @discord.ui.button(emoji='🔁', style=discord.ButtonStyle.secondary)
    async def loop_(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.player
        player.loop = not player.loop

        vc = interaction.guild.voice_client
        self.update_buttons(vc)
        embed = self.player.create_embed(vc)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji='⏹️', style=discord.ButtonStyle.danger)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.player._cog.cleanup(interaction.guild)
        await interaction.response.send_message('Berhenti dan keluar.', ephemeral=True)


def _format_duration(ms: int) -> str:
    seconds = ms // 1000
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f'{hours:02}:{minutes:02}:{sec:02}'
    return f'{minutes:02}:{sec:02}'


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}
        self.locks = {}
        self.volumes = {}

    async def cleanup(self, guild):
        # Hapus pemain dari cache terlebih dahulu untuk menghindari status "zombie"
        player = self.players.pop(guild.id, None)
        self.locks.pop(guild.id, None)

        if player:
            player._stop = True
            if player.np:
                try:
                    await player.np.delete()
                except Exception:
                    pass
                player.np = None

            # Jangan batalkan task jika kita sedang berada di dalam task tersebut (dipanggil dari player_loop)
            current_task = asyncio.current_task()
            if player._task and not player._task.done() and player._task != current_task:
                player._task.cancel()

        # Pastikan koneksi suara terputus
        vc = guild.voice_client
        if vc:
            try:
                await vc.disconnect(force=True)
            except Exception:
                pass

    async def get_player(self, ctx):
        guild_id = ctx.guild.id
        if guild_id not in self.locks:
            self.locks[guild_id] = asyncio.Lock()
        async with self.locks[guild_id]:
            player = self.players.get(guild_id)
            if not player or (player._task and player._task.done()):
                # Jika pemain ada tapi task sudah selesai, bersihkan dulu
                if player:
                    await self.cleanup(ctx.guild)
                self.players[guild_id] = MusicPlayer(ctx)
            return self.players[guild_id]

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.id == self.bot.user.id:
            if after.channel is None:
                await self.cleanup(member.guild)
            return

        vc = member.guild.voice_client
        if not vc or not vc.channel:
            return

        # Jika bot sendirian di channel
        if len([m for m in vc.channel.members if not m.bot]) == 0:
            # Tunggu sebentar (30 detik) sebelum disconnect untuk memberi kesempatan user bergabung kembali
            await asyncio.sleep(30)

            # Cek kembali setelah 30 detik
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

        if not ctx.author.voice:
            return await ctx.send('Kamu tidak terhubung ke saluran suara.')

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

        if not await self._ensure_voice(ctx):
            return

        player = await self.get_player(ctx)

        if isinstance(track, wavelink.Playlist):
            for t in track.tracks:
                t.requester = ctx.author
                await player.queue.put(t)
            embed = discord.Embed(title='Daftar Putar Ditambahkan', color=0xFFC0CB)
            embed.description = f'[{track.name}]({track.url}) — {len(track.tracks)} lagu'
            if track.artwork:
                embed.set_thumbnail(url=track.artwork)
        else:
            track.requester = ctx.author
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
        await ctx.defer(ephemeral=True)
        if not await self._ensure_node(ctx): return
        vc = ctx.voice_client
        if not vc or not isinstance(vc, wavelink.Player):
            return await ctx.send('Tidak terhubung.', ephemeral=True)
        if vc.playing:
            await vc.pause(True)
            player = await self.get_player(ctx)
            if player.np:
                view = player.np.view
                if view: view.update_buttons(vc)
                await player.np.edit(embed=player.create_embed(vc), view=view)
            await ctx.send('Jeda.', ephemeral=True)
        else:
            await ctx.send('Tidak ada yang sedang diputar.', ephemeral=True)

    @commands.hybrid_command(name='resume')
    async def resume_(self, ctx):
        """Melanjutkan musik yang dijeda."""
        await ctx.defer(ephemeral=True)
        if not await self._ensure_node(ctx): return
        vc = ctx.voice_client
        if not vc or not isinstance(vc, wavelink.Player):
            return await ctx.send('Tidak terhubung.', ephemeral=True)
        if vc.paused:
            await vc.pause(False)
            player = await self.get_player(ctx)
            if player.np:
                view = player.np.view
                if view: view.update_buttons(vc)
                await player.np.edit(embed=player.create_embed(vc), view=view)
            await ctx.send('Dilanjutkan.', ephemeral=True)
        else:
            await ctx.send('Tidak sedang dijeda.', ephemeral=True)

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
        await ctx.defer(ephemeral=True)
        if not await self._ensure_node(ctx): return
        vc = ctx.voice_client
        if not vc or not isinstance(vc, wavelink.Player):
            return await ctx.send('Tidak terhubung.', ephemeral=True)
        if not 0 < vol <= 100:
            return await ctx.send('Volume tidak valid (1-100).', ephemeral=True)
        await vc.set_volume(vol)
        self.volumes[ctx.guild.id] = vol
        player = await self.get_player(ctx)
        player.volume = vol
        if player.np:
            view = player.np.view
            if view: view.update_buttons(vc)
            await player.np.edit(embed=player.create_embed(vc), view=view)
        await ctx.send(f'Volume set to {vol}%.', ephemeral=True)

    @commands.hybrid_command(name='nowplaying', aliases=['np'])
    async def nowplaying_(self, ctx):
        """Menampilkan trek yang sedang diputar."""
        vc = ctx.voice_client
        if not vc or not isinstance(vc, wavelink.Player) or not vc.playing:
            return await ctx.send('Tidak ada yang sedang diputar.')

        player = await self.get_player(ctx)
        embed = player.create_embed(vc)
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
        vc = ctx.voice_client
        if vc and player.np:
            view = player.np.view
            if view: view.update_buttons(vc)
            await player.np.edit(embed=player.create_embed(vc), view=view)
        await ctx.send(f'Loop {"On" if player.loop else "Off"}.', ephemeral=True)

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
