import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import os
import subprocess
import sys
from collections import deque

# ==================== AGGRESIVE OPUS FIX ====================
print("=" * 60)
print("INITIALIZING DISCORD MUSIC BOT - OPUS FIX VERSION")
print("=" * 60)

# Force install opus jika tidak ada
print("Checking Opus library...")
if not discord.opus.is_loaded():
    print("WARNING: Opus not loaded. Force installing...")
    
    # Try aggressive installation for Railway
    try:
        # Update apt and install opus
        print("Installing opus via apt-get...")
        subprocess.run(['apt-get', 'update'], check=False, capture_output=True)
        result = subprocess.run(
            ['apt-get', 'install', '-y', 'libopus-dev', 'libopus0', 'libsodium-dev', 'ffmpeg'],
            check=False,
            capture_output=True,
            text=True
        )
        print(f"Install result: {result.returncode}")
        if result.stdout:
            print(f"stdout: {result.stdout[:500]}")
        
        # Set OPUS_LIB_PATH environment variable
        os.environ['OPUS_LIB_PATH'] = '/usr/lib/x86_64-linux-gnu/libopus.so.0'
        
        # Try to load opus
        discord.opus.load_opus('opus')
        
        if not discord.opus.is_loaded():
            # Try specific path
            opus_paths = [
                '/usr/lib/x86_64-linux-gnu/libopus.so.0',
                '/usr/lib/libopus.so.0',
                'libopus.so.0',
                'opus',
                '/app/.apt/usr/lib/x86_64-linux-gnu/libopus.so.0',
            ]
            
            for path in opus_paths:
                try:
                    discord.opus.load_opus(path)
                    if discord.opus.is_loaded():
                        print(f"SUCCESS: Loaded opus from {path}")
                        break
                except Exception as e:
                    print(f"Failed to load from {path}: {e}")
        
    except Exception as e:
        print(f"Install error: {e}")

print(f"Opus loaded status: {discord.opus.is_loaded()}")
print("=" * 60)

# ==================== BOT SETUP ====================
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.members = True

class MusicBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        
    async def setup_hook(self):
        # Remove default help command
        self.remove_command('help')

bot = MusicBot()

# ==================== MUSIC QUEUE ====================
music_queues = {}

# ==================== YT-DLP OPTIONS ====================
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'cookiefile': None,
    'no_check_certificate': True,
    'geo_bypass': True,
    'extractor_retries': 3,
    'socket_timeout': 30,
    'noprogress': True,
}

# ==================== FFMPEG OPTIONS ====================
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin',
    'options': '-vn -acodec libopus -b:a 96k -f opus'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

# ==================== AUDIO SOURCE CLASS ====================
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.webpage_url = data.get('webpage_url', data.get('url'))

    @classmethod
    async def from_url(cls, url, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        
        try:
            data = await loop.run_in_executor(
                None, 
                lambda: ytdl.extract_info(url, download=False)
            )
            
            if 'entries' in data:
                data = data['entries'][0]
            
            audio_url = data['url']
            
            return cls(discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS), data=data)
            
        except Exception as e:
            print(f"Error in YTDLSource.from_url: {e}")
            raise

# ==================== HELPER FUNCTIONS ====================
def get_queue(guild_id):
    if guild_id not in music_queues:
        music_queues[guild_id] = {
            'queue': deque(),
            'current': None,
            'loop': False,
            'loop_queue': False
        }
    return music_queues[guild_id]

async def play_next(ctx):
    guild_id = ctx.guild.id
    queue_data = get_queue(guild_id)
    
    voice_client = ctx.guild.voice_client
    
    if not voice_client or not voice_client.is_connected():
        return
    
    # Get next song
    song = None
    
    if queue_data['loop'] and queue_data['current']:
        song = queue_data['current']
    elif queue_data['loop_queue'] and queue_data['queue']:
        if queue_data['current']:
            queue_data['queue'].append(queue_data['current'])
        song = queue_data['queue'].popleft()
        queue_data['current'] = song
    elif queue_data['queue']:
        song = queue_data['queue'].popleft()
        queue_data['current'] = song
    else:
        queue_data['current'] = None
        await ctx.channel.send("Queue telah habis!")
        return
    
    if not song:
        return
    
    try:
        player = await YTDLSource.from_url(song['url'], loop=bot.loop)
        player.volume = 0.5
        
        def after_playing(error):
            if error:
                print(f'Player error: {error}')
            
            asyncio.run_coroutine_threadsafe(
                play_next(ctx), 
                bot.loop
            )
        
        voice_client.play(player, after=after_playing)
        
        embed = discord.Embed(
            title="Now Playing",
            description=f"**{song['title']}**",
            color=discord.Color.green()
        )
        if song.get('webpage_url'):
            embed.add_field(name="Link", value=f"[Click here]({song['webpage_url']})", inline=False)
        
        if queue_data['loop']:
            embed.set_footer(text="Loop: ON (Single)")
        elif queue_data['loop_queue']:
            embed.set_footer(text="Loop: ON (Queue)")
        
        await ctx.channel.send(embed=embed)
        
    except Exception as e:
        print(f"Error playing song: {e}")
        await ctx.channel.send(f"Error memutar lagu: {str(e)[:100]}")
        await asyncio.sleep(1)
        await play_next(ctx)

# ==================== BOT EVENTS ====================
@bot.event
async def on_ready():
    print('=' * 60)
    print(f'Music Bot {bot.user} ONLINE!')
    print(f'Connected to {len(bot.guilds)} server(s)')
    print(f'Opus loaded: {discord.opus.is_loaded()}')
    print('=' * 60)
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="/play"
        )
    )
    
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} slash command(s)')
    except Exception as e:
        print(f'Error syncing commands: {e}')
    
    print('=' * 60)

# ==================== SLASH COMMANDS ====================
@bot.tree.command(name="play", description="Putar musik dari YouTube")
@app_commands.describe(query="URL YouTube atau kata kunci pencarian")
async def play(interaction: discord.Interaction, query: str):
    await interaction.response.defer(thinking=True)
    
    if not interaction.user.voice:
        await interaction.followup.send("Kamu harus join voice channel dulu!", ephemeral=True)
        return
    
    voice_channel = interaction.user.voice.channel
    
    if not voice_channel.permissions_for(interaction.guild.me).connect:
        await interaction.followup.send("Bot tidak punya permission untuk join voice channel!", ephemeral=True)
        return
    
    if not voice_channel.permissions_for(interaction.guild.me).speak:
        await interaction.followup.send("Bot tidak punya permission untuk speak di voice channel!", ephemeral=True)
        return
    
    if not discord.opus.is_loaded():
        await interaction.followup.send("ERROR: Audio library tidak terload. Bot tidak bisa memutar musik.")
        return
    
    voice_client = interaction.guild.voice_client
    
    if not voice_client:
        try:
            # IMPORTANT: Use different approach for Railway
            voice_client = await voice_channel.connect(
                timeout=30.0,
                reconnect=True,
                self_deaf=True
            )
            print(f"Connected to voice channel: {voice_channel.name}")
        except asyncio.TimeoutError:
            await interaction.followup.send("Timeout saat connect ke voice channel")
            return
        except Exception as e:
            await interaction.followup.send(f"Gagal connect ke voice channel: {str(e)}")
            return
    elif voice_client.channel != voice_channel:
        try:
            await voice_client.move_to(voice_channel)
            print(f"Moved to voice channel: {voice_channel.name}")
        except Exception as e:
            await interaction.followup.send(f"Gagal pindah ke voice channel: {str(e)}")
            return
    
    try:
        print(f"Searching for: {query}")
        
        if not query.startswith(('http://', 'https://', 'www.')):
            search_query = f"ytsearch:{query}"
        else:
            search_query = query
        
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, 
            lambda: ytdl.extract_info(search_query, download=False)
        )
        
        if 'entries' in data:
            if data['entries']:
                data = data['entries'][0]
            else:
                await interaction.followup.send("Tidak ditemukan hasil untuk pencarian tersebut")
                return
        
        song = {
            'url': data.get('url') or data.get('webpage_url'),
            'title': data.get('title', 'Unknown Title'),
            'webpage_url': data.get('webpage_url', data.get('url')),
            'duration': data.get('duration', 0),
            'requester': interaction.user.name
        }
        
        if not song['url']:
            await interaction.followup.send("Tidak bisa mendapatkan URL audio")
            return
        
        queue_data = get_queue(interaction.guild.id)
        
        if not voice_client.is_playing() and not voice_client.is_paused():
            queue_data['current'] = song
            
            try:
                player = await YTDLSource.from_url(song['url'], loop=bot.loop)
                player.volume = 0.5
                
                def after_playing(error):
                    if error:
                        print(f'Play error: {error}')
                    
                    asyncio.run_coroutine_threadsafe(
                        play_next(interaction), 
                        bot.loop
                    )
                
                voice_client.play(player, after=after_playing)
                
                embed = discord.Embed(
                    title="Now Playing",
                    description=f"**{song['title']}**",
                    color=discord.Color.green()
                )
                embed.add_field(name="Requested by", value=interaction.user.mention, inline=False)
                if song.get('webpage_url'):
                    embed.add_field(name="Link", value=f"[Click here]({song['webpage_url']})", inline=False)
                
                await interaction.followup.send(embed=embed)
                
            except Exception as e:
                print(f"Error in immediate play: {e}")
                await interaction.followup.send(f"Error memutar lagu: {str(e)[:200]}")
        
        else:
            queue_data['queue'].append(song)
            
            embed = discord.Embed(
                title="Added to Queue",
                description=f"**{song['title']}**",
                color=discord.Color.blue()
            )
            embed.add_field(name="Position", value=f"#{len(queue_data['queue'])}", inline=True)
            embed.add_field(name="Requested by", value=interaction.user.mention, inline=True)
            
            await interaction.followup.send(embed=embed)
    
    except yt_dlp.utils.DownloadError as e:
        await interaction.followup.send(f"Error download: {str(e)[:200]}")
    except Exception as e:
        print(f"Unexpected error in play: {e}")
        await interaction.followup.send(f"Terjadi error: {str(e)[:200]}")

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
    elif voice_client and not voice_client.is_playing():
        queue_data = get_queue(interaction.guild.id)
        if queue_data['current'] or queue_data['queue']:
            await interaction.response.send_message("Memulai kembali musik...")
            await play_next(interaction)
        else:
            await interaction.response.send_message("Tidak ada musik di queue", ephemeral=True)
    else:
        await interaction.response.send_message("Musik tidak sedang di-pause", ephemeral=True)

@bot.tree.command(name="skip", description="Skip ke lagu berikutnya")
async def skip(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
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
        queue_data['loop_queue'] = False
        
        if voice_client.is_playing() or voice_client.is_paused():
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
        current_time = ""
        if queue_data['current'].get('duration'):
            minutes = queue_data['current']['duration'] // 60
            seconds = queue_data['current']['duration'] % 60
            current_time = f" ({minutes}:{seconds:02d})"
        
        embed.add_field(
            name="Now Playing",
            value=f"**{queue_data['current']['title']}**{current_time}",
            inline=False
        )
    
    if queue_data['queue']:
        queue_list = []
        for i, song in enumerate(list(queue_data['queue'])[:15]):
            time_str = ""
            if song.get('duration'):
                minutes = song['duration'] // 60
                seconds = song['duration'] % 60
                time_str = f" ({minutes}:{seconds:02d})"
            
            requester = song.get('requester', 'Unknown')
            queue_list.append(f"{i+1}. {song['title']}{time_str} - {requester}")
        
        queue_text = "\n".join(queue_list)
        
        if len(queue_data['queue']) > 15:
            queue_text += f"\n\n...dan {len(queue_data['queue']) - 15} lagu lainnya"
        
        embed.add_field(
            name=f"Up Next ({len(queue_data['queue'])} songs)",
            value=queue_text,
            inline=False
        )
    else:
        embed.add_field(
            name="Up Next",
            value="Tidak ada lagu dalam queue",
            inline=False
        )
    
    footer = ""
    if queue_data['loop']:
        footer += "Loop: ON (Single) "
    if queue_data['loop_queue']:
        footer += "Loop: ON (Queue) "
    
    if footer:
        embed.set_footer(text=footer.strip())
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="loop", description="Toggle loop untuk lagu saat ini")
async def loop(interaction: discord.Interaction):
    queue_data = get_queue(interaction.guild.id)
    
    if not queue_data['current']:
        await interaction.response.send_message("Tidak ada lagu yang sedang diputar", ephemeral=True)
        return
    
    queue_data['loop'] = not queue_data['loop']
    
    if queue_data['loop']:
        queue_data['loop_queue'] = False
    
    status = "ON" if queue_data['loop'] else "OFF"
    await interaction.response.send_message(f"Loop mode: {status}")

@bot.tree.command(name="loopqueue", description="Toggle loop untuk seluruh queue")
async def loopqueue(interaction: discord.Interaction):
    queue_data = get_queue(interaction.guild.id)
    
    queue_data['loop_queue'] = not queue_data['loop_queue']
    
    if queue_data['loop_queue']:
        queue_data['loop'] = False
    
    status = "ON" if queue_data['loop_queue'] else "OFF"
    await interaction.response.send_message(f"Queue loop mode: {status}")

@bot.tree.command(name="leave", description="Bot keluar dari voice channel")
async def leave(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if voice_client:
        guild_id = interaction.guild.id
        if guild_id in music_queues:
            queue_data = music_queues[guild_id]
            queue_data['queue'].clear()
            queue_data['current'] = None
            queue_data['loop'] = False
            queue_data['loop_queue'] = False
        
        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
        
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
            description=f"**{queue_data['current']['title']}**",
            color=discord.Color.green()
        )
        
        if queue_data['current'].get('duration'):
            minutes = queue_data['current']['duration'] // 60
            seconds = queue_data['current']['duration'] % 60
            embed.add_field(name="Duration", value=f"{minutes}:{seconds:02d}", inline=True)
        
        if queue_data['current'].get('webpage_url'):
            embed.add_field(name="Link", value=f"[YouTube]({queue_data['current']['webpage_url']})", inline=True)
        
        if queue_data['current'].get('requester'):
            embed.add_field(name="Requested by", value=queue_data['current']['requester'], inline=True)
        
        footer = ""
        if queue_data['loop']:
            footer += "Loop: ON (Single) "
        if queue_data['loop_queue']:
            footer += "Loop: ON (Queue) "
        
        if footer:
            embed.set_footer(text=footer.strip())
        
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("Tidak ada lagu yang sedang diputar", ephemeral=True)

# ==================== RUN BOT ====================
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    print("ERROR: DISCORD_TOKEN tidak ditemukan di environment variables!")
    
    try:
        from dotenv import load_dotenv
        load_dotenv()
        TOKEN = os.getenv("DISCORD_TOKEN")
        if TOKEN:
            print("Token ditemukan di .env file")
    except:
        pass

if TOKEN:
    print(f"Token ditemukan: {TOKEN[:20]}...")
    
    print("\n" + "=" * 60)
    print("SYSTEM INFORMATION")
    print("=" * 60)
    print(f"Python: {sys.version}")
    print(f"Discord.py: {discord.__version__}")
    print(f"YT-DLP: {yt_dlp.__version__}")
    print(f"Opus: {'Loaded' if discord.opus.is_loaded() else 'Not loaded'}")
    print("=" * 60 + "\n")
    
    try:
        bot.run(TOKEN, reconnect=True)
    except discord.LoginFailure:
        print("ERROR: Token invalid! Pastikan token benar.")
    except Exception as e:
        print(f"ERROR: {e}")
else:
    print("ERROR: Tidak bisa mendapatkan DISCORD_TOKEN!")
