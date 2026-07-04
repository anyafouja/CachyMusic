import asyncio
import discord
import random
import itertools
from discord.ext import commands
import wavelink
from .image_gen import generate_progress_bar_image


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

    async def create_embed_data(self, vc: wavelink.Player):
        track = self.current
        if not track:
            return None, None

        embed = discord.Embed(color=0xffc0cb)
        embed.set_author(name="Now playing")

        req_mention = track.requester.mention if hasattr(track, 'requester') else "Unknown"
        loop_status = "On" if self.loop else "Off"

        # Exact layout from reference image
        description = f"**[{track.title[:100]}]({track.uri})**\n"
        description += f"• Added by {req_mention}\n"

        vc_name = vc.channel.name if vc.channel else "Unknown"
        description += f"• Channel: {vc_name}\n\n"

        description += f"Queue Size: `{self.queue.qsize()}` · Volume: `{self.volume}%` · Loop: `{loop_status}`\n"

        # Real graphical progress bar via attachment
        buffer = await generate_progress_bar_image(vc.position, track.length)
        file = discord.File(buffer, filename="progress.png")
        embed.set_image(url="attachment://progress.png")

        embed.description = description

        return embed, file

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
                        # Wait for a new track or timeout after 3 minutes (180s) of inactivity
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
                    embed, file = await self.create_embed_data(vc)
                    if self.np:
                        try:
                            await self.np.delete()
                        except Exception:
                            pass
                    self.np = await self._channel.send(embed=embed, file=file, view=view)
                except Exception:
                    pass

                try:
                    count = 0
                    while (vc.playing or vc.paused) and self._guild.voice_client:
                        await asyncio.sleep(2)
                        count += 1

                        # Refresh UI every 10 seconds
                        if count % 5 == 0 and self.np:
                            try:
                                view.update_buttons(vc)
                                embed, file = await self.create_embed_data(vc)
                                await self.np.edit(embed=embed, attachments=[file], view=view)
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

                # Disconnect immediately if the queue is empty after a track ends
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
            await interaction.response.send_message('Not for this server.', ephemeral=True)
            return False
        vc = interaction.guild.voice_client
        if not vc or not vc.channel:
            await interaction.response.send_message('Not connected to voice.', ephemeral=True)
            return False
        if interaction.user not in vc.channel.members:
            await interaction.response.send_message('Join the voice channel first.', ephemeral=True)
            return False
        return True

    def update_buttons(self, vc: wavelink.Player):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                # Update symbols based on state
                if child.label in ['\u23F8', '\u25B6']: # Pause/Play
                    child.label = '\u25B6' if vc.paused else '\u23F8'
                if child.label == '\uD83D\uDD04': # Loop
                    child.style = discord.ButtonStyle.success if self.player.loop else discord.ButtonStyle.secondary

    @discord.ui.button(label='\u23EE', style=discord.ButtonStyle.secondary) # Previous
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.player
        if not player.current:
            return await interaction.response.send_message('Nothing is playing.', ephemeral=True)
        if not player.history:
            return await interaction.response.send_message('No previous tracks.', ephemeral=True)
        player._next_up = player.history.pop()
        player._stop = True
        vc = interaction.guild.voice_client
        if vc:
            await vc.stop()
        await interaction.response.defer()

    @discord.ui.button(label='\u23F8', style=discord.ButtonStyle.secondary) # Pause
    async def pause_play(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if not vc or not isinstance(vc, wavelink.Player):
            return await interaction.response.send_message('Not connected.', ephemeral=True)
        if vc.paused:
            await vc.pause(False)
        elif vc.playing:
            await vc.pause(True)
        else:
            return await interaction.response.send_message('Nothing is playing.', ephemeral=True)

        self.update_buttons(vc)
        embed, file = await self.player.create_embed_data(vc)
        await interaction.response.edit_message(embed=embed, attachments=[file], view=self)

    @discord.ui.button(label='\u23ED', style=discord.ButtonStyle.secondary) # Skip
    async def next_(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.player
        if not player.current:
            return await interaction.response.send_message('Nothing is playing.', ephemeral=True)
        player._stop = True
        vc = interaction.guild.voice_client
        if vc:
            await vc.stop()
        await interaction.response.defer()

    @discord.ui.button(label='\uD83D\uDD04', style=discord.ButtonStyle.secondary) # Loop
    async def loop_(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.player
        player.loop = not player.loop

        vc = interaction.guild.voice_client
        self.update_buttons(vc)
        embed, file = await self.player.create_embed_data(vc)
        await interaction.response.edit_message(embed=embed, attachments=[file], view=self)

    @discord.ui.button(label='\u23F9', style=discord.ButtonStyle.secondary) # Stop
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.player._cog.cleanup(interaction.guild)
        await interaction.response.send_message('Stopped.', ephemeral=True)


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
        # Remove player from cache first to avoid "zombie" states
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

            # Don't cancel task if we are inside it
            current_task = asyncio.current_task()
            if player._task and not player._task.done() and player._task != current_task:
                player._task.cancel()

        # Ensure voice client is disconnected
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

        # If bot is alone in channel
        if len([m for m in vc.channel.members if not m.bot]) == 0:
            await asyncio.sleep(30)
            vc = member.guild.voice_client
            if vc and vc.channel and len([m for m in vc.channel.members if not m.bot]) == 0:
                await self.cleanup(member.guild)

    async def _ensure_voice(self, ctx) -> bool:
        vc = ctx.voice_client
        if not ctx.author.voice:
            await ctx.send('You are not connected to a voice channel.')
            return False
        target = ctx.author.voice.channel
        if not vc:
            if not await self.bot.ensure_node():
                await ctx.send('Lavalink node not available - try again later.')
                return False
            try:
                vc = await target.connect(cls=wavelink.Player, reconnect=True)
            except Exception:
                await self.cleanup(ctx.guild)
                await asyncio.sleep(1)
                vc = await target.connect(cls=wavelink.Player, reconnect=True)
        elif vc.channel != target:
            await vc.move_to(target)
        return True

    async def _ensure_node(self, ctx) -> bool:
        if not await self.bot.ensure_node():
            await ctx.send('Lavalink node not available - try again later.')
            return False
        return True

    @commands.hybrid_command(name='play', aliases=['p'])
    async def play_(self, ctx, *, search: str):
        """Plays a song from YouTube or SoundCloud."""
        await ctx.defer()
        if not ctx.author.voice:
            return await ctx.send('You are not connected to a voice channel.')
        try:
            tracks = await wavelink.Playable.search(search, source=wavelink.TrackSource.YouTube)
            if not tracks:
                tracks = await wavelink.Playable.search(search, source=wavelink.TrackSource.SC)
            if not tracks:
                return await ctx.send('No results found.')
            track = tracks if isinstance(tracks, wavelink.Playlist) else tracks[0]
        except Exception as e:
            return await ctx.send(f'Search failed: `{e}`')

        if not await self._ensure_voice(ctx):
            return
        player = await self.get_player(ctx)

        if isinstance(track, wavelink.Playlist):
            for t in track.tracks:
                t.requester = ctx.author
                await player.queue.put(t)
            embed = discord.Embed(title='Playlist Added', color=0xFFC0CB)
            embed.description = f'[{track.name}]({track.url}) — {len(track.tracks)} tracks'
            if track.artwork:
                embed.set_thumbnail(url=track.artwork)
        else:
            track.requester = ctx.author
            await player.queue.put(track)
            embed = discord.Embed(title='Added to Queue', color=0xFFC0CB)
            embed.description = f'[{track.title}]({track.uri})'
            if track.artwork:
                embed.set_thumbnail(url=track.artwork)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='skip', aliases=['s'])
    async def skip_(self, ctx):
        """Skips the current song."""
        await ctx.defer(ephemeral=True)
        if not await self._ensure_node(ctx): return
        vc = ctx.voice_client
        if not vc or not (getattr(vc, 'playing', False) or getattr(vc, 'paused', False)):
            return await ctx.send('Nothing is playing.', ephemeral=True)
        player = await self.get_player(ctx)
        player._stop = True
        await vc.stop()
        player.current = None
        await ctx.send('Skipped.', ephemeral=True)

    @commands.hybrid_command(name='stop')
    async def stop_(self, ctx):
        """Stops the music and disconnects the bot."""
        await ctx.defer(ephemeral=True)
        if not await self._ensure_node(ctx): return
        vc = ctx.voice_client
        if not vc or not vc.connected:
            return await ctx.send('Not connected.', ephemeral=True)
        await self.cleanup(ctx.guild)
        await ctx.send('Stopped.', ephemeral=True)

    @commands.hybrid_command(name='pause')
    async def pause_(self, ctx):
        """Pauses the music."""
        await ctx.defer(ephemeral=True)
        if not await self._ensure_node(ctx): return
        vc = ctx.voice_client
        if not vc or not isinstance(vc, wavelink.Player):
            return await ctx.send('Not connected.', ephemeral=True)
        if vc.playing:
            await vc.pause(True)
            player = await self.get_player(ctx)
            if player.np:
                view = player.np.view
                if view: view.update_buttons(vc)
                embed, file = await player.create_embed_data(vc)
                await player.np.edit(embed=embed, attachments=[file], view=view)
            await ctx.send('Paused.', ephemeral=True)
        else:
            await ctx.send('Nothing is playing.', ephemeral=True)

    @commands.hybrid_command(name='resume')
    async def resume_(self, ctx):
        """Resumes paused music."""
        await ctx.defer(ephemeral=True)
        if not await self._ensure_node(ctx): return
        vc = ctx.voice_client
        if not vc or not isinstance(vc, wavelink.Player):
            return await ctx.send('Not connected.', ephemeral=True)
        if vc.paused:
            await vc.pause(False)
            player = await self.get_player(ctx)
            if player.np:
                view = player.np.view
                if view: view.update_buttons(vc)
                embed, file = await player.create_embed_data(vc)
                await player.np.edit(embed=embed, attachments=[file], view=view)
            await ctx.send('Resumed.', ephemeral=True)
        else:
            await ctx.send('Not paused.', ephemeral=True)

    @commands.hybrid_command(name='queue', aliases=['q'])
    async def queue_info(self, ctx):
        """Shows current queue."""
        player = await self.get_player(ctx)
        if player.queue.empty():
            return await ctx.send('Queue is empty.')
        upcoming = list(itertools.islice(player.queue._queue, 0, 10))
        fmt = '\n'.join(f"**{i+1}.** {item.title}" for i, item in enumerate(upcoming))
        await ctx.send(embed=discord.Embed(title='Queue', description=fmt, color=0xFFC0CB))

    @commands.hybrid_command(name='volume', aliases=['vol'])
    async def change_volume(self, ctx, vol: int):
        """Sets bot volume (1-100)."""
        await ctx.defer(ephemeral=True)
        if not await self._ensure_node(ctx): return
        vc = ctx.voice_client
        if not vc or not isinstance(vc, wavelink.Player):
            return await ctx.send('Not connected.', ephemeral=True)
        if not 0 < vol <= 100:
            return await ctx.send('Invalid volume (1-100).', ephemeral=True)
        await vc.set_volume(vol)
        self.volumes[ctx.guild.id] = vol
        player = await self.get_player(ctx)
        player.volume = vol
        if player.np:
            view = player.np.view
            if view: view.update_buttons(vc)
            embed, file = await player.create_embed_data(vc)
            await player.np.edit(embed=embed, attachments=[file], view=view)
        await ctx.send(f'Volume set to {vol}%.', ephemeral=True)

    @commands.hybrid_command(name='nowplaying', aliases=['np'])
    async def nowplaying_(self, ctx):
        """Shows currently playing track."""
        vc = ctx.voice_client
        if not vc or not isinstance(vc, wavelink.Player) or not vc.playing:
            return await ctx.send('Nothing is playing.', ephemeral=True)
        player = await self.get_player(ctx)
        embed, file = await player.create_embed_data(vc)
        await ctx.send(embed=embed, file=file)

    @commands.hybrid_command(name='help')
    async def help_(self, ctx):
        """Shows all commands."""
        cmds = [
            ('play <query>', 'Search & play from YouTube / SoundCloud'),
            ('skip', 'Skip current song'),
            ('stop', 'Stop and disconnect'),
            ('pause', 'Pause playback'),
            ('resume', 'Resume playback'),
            ('volume <1-100>', 'Set volume'),
            ('queue', 'Show current queue'),
            ('nowplaying', 'Show current track info'),
            ('clear-queue', 'Clear all queued tracks'),
            ('shuffle', 'Shuffle the queue'),
            ('loop', 'Toggle loop mode'),
            ('ping', 'Check bot latency'),
        ]
        embed = discord.Embed(title='Cachy Music', color=0xFFC0CB)
        embed.description = '\n\n'.join(f'**cachy {cmd}**\n{desc}' for cmd, desc in cmds)
        embed.set_footer(text='Powered by Lavalink | YouTube + SoundCloud')
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='ping')
    async def ping_(self, ctx):
        """Checks bot latency."""
        await ctx.send(embed=discord.Embed(description=f'Pong! {round(self.bot.latency * 1000)}ms', color=0xFFC0CB))

    @commands.hybrid_command(name='clear-queue')
    async def clear_queue_(self, ctx):
        """Clears all songs from the queue."""
        player = await self.get_player(ctx)
        while not player.queue.empty():
            try:
                player.queue.get_nowait()
            except Exception:
                break
        await ctx.send(embed=discord.Embed(description='Queue cleared', color=0xFFC0CB))

    @commands.hybrid_command(name='loop')
    async def loop_(self, ctx):
        """Toggles looping of current song."""
        player = await self.get_player(ctx)
        player.loop = not player.loop
        vc = ctx.voice_client
        if vc and player.np:
            view = player.np.view
            if view: view.update_buttons(vc)
            embed, file = await player.create_embed_data(vc)
            await player.np.edit(embed=embed, attachments=[file], view=view)
        await ctx.send(f'Loop {"On" if player.loop else "Off"}.', ephemeral=True)

    @commands.hybrid_command(name='shuffle')
    async def shuffle_(self, ctx):
        """Shuffles the queue."""
        player = await self.get_player(ctx)
        if player.queue.empty():
            return await ctx.send('Queue is empty.')
        songs = []
        while not player.queue.empty():
            try:
                songs.append(player.queue.get_nowait())
            except Exception:
                break
        random.shuffle(songs)
        for song in songs:
            await player.queue.put(song)
        await ctx.send(embed=discord.Embed(description='Shuffled', color=0xFFC0CB))


async def setup(bot):
    await bot.add_cog(Music(bot))
