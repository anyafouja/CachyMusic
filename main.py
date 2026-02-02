import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import os
from collections import deque

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

music_queues = {}

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'cookiefile': None,
    'no_check_certificate': True,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')

    @classmethod
    async def from_url(cls, url, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url']
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)

def get_queue(guild_id):
    if guild_id not in music_queues:
        music_queues[guild_id] = {
            'queue': deque(),
            'current': None,
            'loop': False
        }
    return music_queues[guild_id]

async def play_next(interaction):
    guild_id = interaction.guild.id
    queue_data = get_queue(guild_id)
    
    voice_client = interaction.guild.voice_client
    
    if not voice_client:
        return
    
    if queue_data['loop'] and queue_data['current']:
        url = queue_data['current']['url']
        title = queue_data['current']['title']
    elif queue_data['queue']:
        song = queue_data['queue'].popleft()
        url = song['url']
        title = song['title']
        queue_data['current'] = song
    else:
        queue_data['current'] = None
        return
    
    try:
        player = await YTDLSource.from_url(url, loop=bot.loop)
        voice_client.play(
            player,
            after=lambda e: asyncio.run_coroutine_threadsafe(
                play_next(interaction), bot.loop
            )
        )
    except Exception as e:
        print('Error playing: {}'.format(e))
        await play_next(interaction)

@bot.event
async def on_ready():
    print('=' * 60)
    print('Music Bot {} ONLINE!'.format(bot.user))
    print('Connected to {} server(s)'.format(len(bot.guilds)))
    print('=' * 60)
    try:
        synced = await bot.tree.sync()
        print('Synced {} slash command(s)'.format(len(synced)))
    except Exception as e:
        print('Error syncing commands: {}'.format(e))

@bot.tree.command(name="play", description="Putar musik dari YouTube")
@app_commands.describe(query="URL YouTube atau kata kunci pencarian")
async def play(interaction: discord.Interaction, query: str):
    if not interaction.user.voice:
        await interaction.response.send_message("Kamu harus join voice channel dulu!", ephemeral=True)
        return
    
    channel = interaction.user.voice.channel
    
    await interaction.response.defer()
    
    try:
        if not interaction.guild.voice_client:
            voice_client = await channel.connect(timeout=60.0, reconnect=True)
        elif interaction.guild.voice_client.channel != channel:
            await interaction.guild.voice_client.move_to(channel)
            voice_client = interaction.guild.voice_client
        else:
            voice_client = interaction.guild.voice_client
    except Exception as e:
        await interaction.followup.send("Gagal connect ke voice channel: {}".format(str(e)))
        return
    
    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, 
            lambda: ytdl.extract_info("ytsearch:{}".format(query), download=False)
        )
        
        if 'entries' in data:
            data = data['entries'][0]
        
        song = {
            'url': data['url'],
            'title': data['title'],
            'webpage_url': data['webpage_url'],
            'duration': data.get('duration', 0)
        }
        
        queue_data = get_queue(interaction.guild.id)
        
        if not voice_client.is_playing() and not voice_client.is_paused():
            queue_data['current'] = song
            player = await YTDLSource.from_url(song['url'], loop=bot.loop)
            voice_client.play(
                player,
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    play_next(interaction), bot.loop
                )
            )
            await interaction.followup.send("Sedang memutar: **{}**".format(song['title']))
        else:
            queue_data['queue'].append(song)
            await interaction.followup.send(
                "Ditambahkan ke queue: **{}**\nPosisi dalam queue: {}".format(
                    song['title'], 
                    len(queue_data['queue'])
                )
            )
    
    except Exception as e:
        await interaction.followup.send("Terjadi error: {}".format(str(e)))

@bot.tree.command(name="pause", description="Pause musik yang sedang diputar")
async def pause(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await interaction.response.send_message("Musik di-pause")
    else:
        await interaction.response.send_message("Tidak ada musik yang sedang diputar", ephemeral=True)

@bot.tree.command(name="resume", description="Lanjutkan musik yang di-pause")
async def resume(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await interaction.response.send_message("Musik dilanjutkan")
    else:
        await interaction.response.send_message("Musik tidak sedang di-pause", ephemeral=True)

@bot.tree.command(name="skip", description="Skip ke lagu berikutnya")
async def skip(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await interaction.response.send_message("Lagu di-skip")
    else:
        await interaction.response.send_message("Tidak ada musik yang sedang diputar", ephemeral=True)

@bot.tree.command(name="stop", description="Stop musik dan clear queue")
async def stop(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if voice_client:
        queue_data = get_queue(interaction.guild.id)
        queue_data['queue'].clear()
        queue_data['current'] = None
        queue_data['loop'] = False
        voice_client.stop()
        await interaction.response.send_message("Musik dihentikan dan queue dikosongkan")
    else:
        await interaction.response.send_message("Bot tidak ada di voice channel", ephemeral=True)

@bot.tree.command(name="queue", description="Lihat antrian lagu")
async def queue(interaction: discord.Interaction):
    queue_data = get_queue(interaction.guild.id)
    
    if not queue_data['current'] and not queue_data['queue']:
        await interaction.response.send_message("Queue kosong", ephemeral=True)
        return
    
    embed = discord.Embed(title="Music Queue", color=discord.Color.blue())
    
    if queue_data['current']:
        embed.add_field(
            name="Sedang Diputar",
            value="**{}**".format(queue_data['current']['title']),
            inline=False
        )
    
    if queue_data['queue']:
        queue_list = "\n".join([
            "{}. {}".format(i+1, song['title'])
            for i, song in enumerate(list(queue_data['queue'])[:10])
        ])
        embed.add_field(
            name="Selanjutnya ({} lagu)".format(len(queue_data['queue'])),
            value=queue_list,
            inline=False
        )
    
    if queue_data['loop']:
        embed.set_footer(text="Loop: ON")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="loop", description="Toggle loop untuk lagu saat ini")
async def loop(interaction: discord.Interaction):
    queue_data = get_queue(interaction.guild.id)
    queue_data['loop'] = not queue_data['loop']
    
    status = "ON" if queue_data['loop'] else "OFF"
    await interaction.response.send_message("Loop: **{}**".format(status))

@bot.tree.command(name="leave", description="Bot keluar dari voice channel")
async def leave(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if voice_client:
        queue_data = get_queue(interaction.guild.id)
        queue_data['queue'].clear()
        queue_data['current'] = None
        queue_data['loop'] = False
        await voice_client.disconnect()
        await interaction.response.send_message("Bot keluar dari voice channel")
    else:
        await interaction.response.send_message("Bot tidak ada di voice channel", ephemeral=True)

@bot.tree.command(name="nowplaying", description="Lihat lagu yang sedang diputar")
async def nowplaying(interaction: discord.Interaction):
    queue_data = get_queue(interaction.guild.id)
    
    if queue_data['current']:
        embed = discord.Embed(
            title="Now Playing",
            description="**{}**".format(queue_data['current']['title']),
            color=discord.Color.green()
        )
        embed.add_field(name="Link", value=queue_data['current']['webpage_url'])
        
        if queue_data['loop']:
            embed.set_footer(text="Loop: ON")
        
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("Tidak ada lagu yang sedang diputar", ephemeral=True)

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    print("ERROR: DISCORD_TOKEN tidak ditemukan!")
else:
    try:
        bot.run(TOKEN)
    except Exception as e:
        print("ERROR: {}".format(e))
