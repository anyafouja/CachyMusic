import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import os
import subprocess
import sys
from collections import deque

# ==================== OPUS LOADING FIX ====================
print("=" * 60)
print("INITIALIZING DISCORD MUSIC BOT")
print("=" * 60)

# Cek dan load opus library dengan berbagai metode
print("Checking Opus library...")
if not discord.opus.is_loaded():
    print("Opus not loaded. Attempting to load...")
    
    # Daftar path opus library yang mungkin
    opus_paths = [
        'opus',  # Nama default
        'libopus.so.0',  # Linux standard
        'libopus.0.dylib',  # macOS
        'libopus-0.dll',  # Windows
        '/usr/lib/x86_64-linux-gnu/libopus.so.0',  # Ubuntu/Debian
        '/usr/lib/libopus.so.0',  # General Linux
        '/usr/local/lib/libopus.dylib',  # macOS brew
        '/app/.apt/usr/lib/x86_64-linux-gnu/libopus.so.0',  # Heroku/Railway
    ]
    
    loaded = False
    for path in opus_paths:
        try:
            discord.opus.load_opus(path)
            if discord.opus.is_loaded():
                print(f"✓ Successfully loaded opus from: {path}")
                loaded = True
                break
        except Exception as e:
            print(f"✗ Failed to load from {path}: {e}")
    
    if not loaded:
        # Coba install opus jika tidak ditemukan (untuk Railway/Heroku)
        try:
            print("Attempting to install opus via apt...")
            subprocess.run(['apt-get', 'update'], check=False)
            subprocess.run(['apt-get', 'install', '-y', 'libopus-dev', 'libopus0'], check=False)
            # Coba load lagi setelah install
            discord.opus.load_opus('opus')
        except Exception as e:
            print(f"Failed to install opus: {e}")
    
    if not discord.opus.is_loaded():
        print("⚠ WARNING: Opus library could not be loaded. Audio may not work!")
    else:
        print(f"✓ Opus library loaded successfully. Version: {discord.opus._lib.opus_get_version_string()}")

print(f"Opus loaded status: {discord.opus.is_loaded()}")
print("=" * 60)

# ==================== BOT SETUP ====================
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

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
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'extractor_args': {
        'youtube': {
            'player_client': ['android'],
            'skip': ['dash', 'hls']
        }
    },
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
}

# ==================== FFMPEG OPTIONS FIXED ====================
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -probesize 20M -analyzeduration 20M -loglevel warning',
    'options': '-vn -bufsize 512k -af volume=0.5 -ac 2 -ar 48000'
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
            
            # Dapatkan URL audio terbaik
            if 'url' in data:
                audio_url = data['url']
            elif 'formats' in data:
                # Pilih format audio terbaik
                formats = data['formats']
                audio_formats = [f for f in formats if f.get('acodec') != 'none']
                if audio_formats:
                    # Pilih format dengan bitrate tertinggi
                    best_format = max(audio_formats, key=lambda x: x.get('abr', 0) or 0)
                    audio_url = best_format['url']
                else:
                    raise Exception("No audio format found")
            else:
                raise Exception("No audio URL found")
            
            # Debug info
            print(f"Audio URL obtained: {audio_url[:100]}...")
            
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
    """Play next song in queue"""
    guild_id = ctx.guild.id
    queue_data = get_queue(guild_id)
    
    voice_client = ctx.guild.voice_client
    
    if not voice_client:
        return
    
    # Cek jika bot disconnected
    if not voice_client.is_connected():
        return
    
    # Get next song
    song = None
    
    if queue_data['loop'] and queue_data['current']:
        # Loop single song
        song = queue_data['current']
    elif queue_data['loop_queue'] and queue_data['queue']:
        # Loop queue - put current song back to end
        if queue_data['current']:
            queue_data['queue'].append(queue_data['current'])
        song = queue_data['queue'].popleft()
        queue_data['current'] = song
    elif queue_data['queue']:
        # Normal play next
        song = queue_data['queue'].popleft()
        queue_data['current'] = song
    else:
        # No more songs
        queue_data['current'] = None
        await ctx.channel.send("✅ Queue telah habis!")
        return
    
    if not song:
        return
    
    try:
        # Get player
        player = await YTDLSource.from_url(song['url'], loop=bot.loop)
        
        # Adjust volume
        player.volume = 0.5
        
        def after_playing(error):
            """Callback setelah selesai memutar"""
            if error:
                print(f'Player error: {error}')
            
            # Schedule next song
            asyncio.run_coroutine_threadsafe(
                play_next(ctx), 
                bot.loop
            )
        
        # Play with error handling
        voice_client.play(player, after=after_playing)
        
        # Send now playing message
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"**{song['title']}**",
            color=discord.Color.green()
        )
        if song.get('webpage_url'):
            embed.add_field(name="Link", value=f"[Click here]({song['webpage_url']})", inline=False)
        
        if queue_data['loop']:
            embed.set_footer(text="🔁 Loop: ON (Single)")
        elif queue_data['loop_queue']:
            embed.set_footer(text="🔁 Loop: ON (Queue)")
        
        await ctx.channel.send(embed=embed)
        
    except Exception as e:
        print(f"Error playing song: {e}")
        await ctx.channel.send(f"❌ Error memutar lagu: {str(e)[:100]}")
        
        # Skip to next song jika error
        await asyncio.sleep(1)
        await play_next(ctx)

# ==================== BOT EVENTS ====================
@bot.event
async def on_ready():
    print('=' * 60)
    print(f'✅ Music Bot {bot.user} ONLINE!')
    print(f'✅ Connected to {len(bot.guilds)} server(s)')
    print(f'✅ Opus loaded: {discord.opus.is_loaded()}')
    print('=' * 60)
    
    # Set bot status
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="🎵 /play"
        )
    )
    
    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f'✅ Synced {len(synced)} slash command(s)')
    except Exception as e:
        print(f'❌ Error syncing commands: {e}')
    
    print('=' * 60)

@bot.event
async def on_voice_state_update(member, before, after):
    """Handle voice state updates for auto-disconnect"""
    if member == bot.user:
        return
    
    # Cek jika bot sendirian di voice channel
    if before.channel and not after.channel:
        # Member left channel
        voice_client = before.channel.guild.voice_client
        
        if voice_client and voice_client.channel == before.channel:
            # Hitung member selain bot
            members = [m for m in before.channel.members if not m.bot]
            
            if len(members) == 0:
                print(f"Bot left alone in {before.channel.name}, disconnecting...")
                
                # Clear queue
                guild_id = before.channel.guild.id
                if guild_id in music_queues:
                    queue_data = music_queues[guild_id]
                    queue_data['queue'].clear()
                    queue_data['current'] = None
                
                # Disconnect dengan delay
                await asyncio.sleep(60)  # Tunggu 1 menit
                
                # Cek lagi apakah masih sendirian
                if voice_client and voice_client.channel == before.channel:
                    members = [m for m in before.channel.members if not m.bot]
                    if len(members) == 0:
                        await voice_client.disconnect()
                        # Kirim message ke default channel
                        try:
                            default_channel = before.channel.guild.system_channel
                            if default_channel:
                                await default_channel.send("👋 Keluar dari voice channel karena tidak ada orang lagi...")
                        except:
                            pass

# ==================== SLASH COMMANDS ====================
@bot.tree.command(name="play", description="Putar musik dari YouTube")
@app_commands.describe(query="URL YouTube atau kata kunci pencarian")
async def play(interaction: discord.Interaction, query: str):
    """Play music from YouTube"""
    # Defer response dulu karena mungkin lama
    await interaction.response.defer(thinking=True)
    
    # Cek user di voice channel
    if not interaction.user.voice:
        await interaction.followup.send("❌ Kamu harus join voice channel dulu!", ephemeral=True)
        return
    
    voice_channel = interaction.user.voice.channel
    
    # Cek permission
    if not voice_channel.permissions_for(interaction.guild.me).connect:
        await interaction.followup.send("❌ Bot tidak punya permission untuk join voice channel!", ephemeral=True)
        return
    
    if not voice_channel.permissions_for(interaction.guild.me).speak:
        await interaction.followup.send("❌ Bot tidak punya permission untuk speak di voice channel!", ephemeral=True)
        return
    
    # Cek opus
    if not discord.opus.is_loaded():
        await interaction.followup.send("❌ Error: Audio library tidak terload. Bot tidak bisa memutar musik.")
        return
    
    # Connect atau move to voice channel
    voice_client = interaction.guild.voice_client
    
    if not voice_client:
        try:
            voice_client = await voice_channel.connect(timeout=60.0, reconnect=True)
            print(f"Connected to voice channel: {voice_channel.name}")
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Timeout saat connect ke voice channel")
            return
        except Exception as e:
            await interaction.followup.send(f"❌ Gagal connect ke voice channel: {str(e)}")
            return
    elif voice_client.channel != voice_channel:
        try:
            await voice_client.move_to(voice_channel)
            print(f"Moved to voice channel: {voice_channel.name}")
        except Exception as e:
            await interaction.followup.send(f"❌ Gagal pindah ke voice channel: {str(e)}")
            return
    
    # Extract song info
    try:
        print(f"Searching for: {query}")
        
        # Cek jika URL atau search query
        if not query.startswith(('http://', 'https://', 'www.')):
            search_query = f"ytsearch:{query}"
        else:
            search_query = query
        
        # Extract info
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, 
            lambda: ytdl.extract_info(search_query, download=False)
        )
        
        # Handle playlist or single
        if 'entries' in data:
            if data['entries']:
                data = data['entries'][0]
            else:
                await interaction.followup.send("❌ Tidak ditemukan hasil untuk pencarian tersebut")
                return
        
        # Create song object
        song = {
            'url': data.get('url') or data.get('webpage_url'),
            'title': data.get('title', 'Unknown Title'),
            'webpage_url': data.get('webpage_url', data.get('url')),
            'duration': data.get('duration', 0),
            'requester': interaction.user.name
        }
        
        if not song['url']:
            # Cari URL dari formats
            if 'formats' in data:
                formats = data['formats']
                audio_formats = [f for f in formats if f.get('acodec') != 'none']
                if audio_formats:
                    best_format = max(audio_formats, key=lambda x: x.get('abr', 0) or 0)
                    song['url'] = best_format['url']
        
        if not song['url']:
            await interaction.followup.send("❌ Tidak bisa mendapatkan URL audio")
            return
        
        # Get queue
        queue_data = get_queue(interaction.guild.id)
        
        # Play atau add to queue
        if not voice_client.is_playing() and not voice_client.is_paused():
            # Play langsung
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
                    title="🎵 Now Playing",
                    description=f"**{song['title']}**",
                    color=discord.Color.green()
                )
                embed.add_field(name="Requested by", value=interaction.user.mention, inline=False)
                if song.get('webpage_url'):
                    embed.add_field(name="Link", value=f"[Click here]({song['webpage_url']})", inline=False)
                
                await interaction.followup.send(embed=embed)
                
            except Exception as e:
                print(f"Error in immediate play: {e}")
                await interaction.followup.send(f"❌ Error memutar lagu: {str(e)[:200]}")
        
        else:
            # Add to queue
            queue_data['queue'].append(song)
            
            embed = discord.Embed(
                title="➕ Added to Queue",
                description=f"**{song['title']}**",
                color=discord.Color.blue()
            )
            embed.add_field(name="Position", value=f"#{len(queue_data['queue'])}", inline=True)
            embed.add_field(name="Requested by", value=interaction.user.mention, inline=True)
            
            await interaction.followup.send(embed=embed)
    
    except yt_dlp.utils.DownloadError as e:
        await interaction.followup.send(f"❌ Error download: {str(e)[:200]}")
    except Exception as e:
        print(f"Unexpected error in play: {e}")
        await interaction.followup.send(f"❌ Terjadi error: {str(e)[:200]}")

@bot.tree.command(name="pause", description="Pause musik yang sedang diputar")
async def pause(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await interaction.response.send_message("⏸️ Musik di-pause")
    else:
        await interaction.response.send_message("❌ Tidak ada musik yang sedang diputar", ephemeral=True)

@bot.tree.command(name="resume", description="Lanjutkan musik yang di-pause")
async def resume(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await interaction.response.send_message("▶️ Musik dilanjutkan")
    elif voice_client and not voice_client.is_playing():
        # Coba play next jika queue ada
        queue_data = get_queue(interaction.guild.id)
        if queue_data['current'] or queue_data['queue']:
            await interaction.response.send_message("🎵 Memulai kembali musik...")
            await play_next(interaction)
        else:
            await interaction.response.send_message("❌ Tidak ada musik di queue", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Musik tidak sedang di-pause", ephemeral=True)

@bot.tree.command(name="skip", description="Skip ke lagu berikutnya")
async def skip(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
        voice_client.stop()
        await interaction.response.send_message("⏭️ Lagu di-skip")
    else:
        await interaction.response.send_message("❌ Tidak ada musik yang sedang diputar", ephemeral=True)

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
        
        await interaction.response.send_message("⏹️ Musik dihentikan dan queue dikosongkan")
    else:
        await interaction.response.send_message("❌ Bot tidak ada di voice channel", ephemeral=True)

@bot.tree.command(name="queue", description="Lihat antrian lagu")
async def queue(interaction: discord.Interaction):
    queue_data = get_queue(interaction.guild.id)
    
    if not queue_data['current'] and not queue_data['queue']:
        await interaction.response.send_message("📭 Queue kosong", ephemeral=True)
        return
    
    embed = discord.Embed(title="🎶 Music Queue", color=discord.Color.blue())
    
    # Current playing
    if queue_data['current']:
        current_time = ""
        if queue_data['current'].get('duration'):
            minutes = queue_data['current']['duration'] // 60
            seconds = queue_data['current']['duration'] % 60
            current_time = f" ({minutes}:{seconds:02d})"
        
        embed.add_field(
            name="🎵 Now Playing",
            value=f"**{queue_data['current']['title']}**{current_time}",
            inline=False
        )
    
    # Queue list
    if queue_data['queue']:
        queue_list = []
        for i, song in enumerate(list(queue_data['queue'])[:15]):  # Limit 15 songs
            time_str = ""
            if song.get('duration'):
                minutes = song['duration'] // 60
                seconds = song['duration'] % 60
                time_str = f" ({minutes}:{seconds:02d})"
            
            requester = song.get('requester', 'Unknown')
            queue_list.append(f"**{i+1}.** {song['title']}{time_str} - *{requester}*")
        
        queue_text = "\n".join(queue_list)
        
        if len(queue_data['queue']) > 15:
            queue_text += f"\n\n...dan {len(queue_data['queue']) - 15} lagu lainnya"
        
        embed.add_field(
            name=f"📜 Up Next ({len(queue_data['queue'])} songs)",
            value=queue_text,
            inline=False
        )
    else:
        embed.add_field(
            name="📜 Up Next",
            value="*Tidak ada lagu dalam queue*",
            inline=False
        )
    
    # Loop status
    footer = ""
    if queue_data['loop']:
        footer += "🔁 Loop: ON (Single) "
    if queue_data['loop_queue']:
        footer += "🔁 Loop: ON (Queue) "
    
    if footer:
        embed.set_footer(text=footer.strip())
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="loop", description="Toggle loop untuk lagu saat ini")
async def loop(interaction: discord.Interaction):
    queue_data = get_queue(interaction.guild.id)
    
    if not queue_data['current']:
        await interaction.response.send_message("❌ Tidak ada lagu yang sedang diputar", ephemeral=True)
        return
    
    queue_data['loop'] = not queue_data['loop']
    
    if queue_data['loop']:
        queue_data['loop_queue'] = False  # Matikan loop queue jika loop single aktif
    
    status = "🔁 **ON**" if queue_data['loop'] else "🔁 **OFF**"
    await interaction.response.send_message(f"Loop mode: {status}")

@bot.tree.command(name="loopqueue", description="Toggle loop untuk seluruh queue")
async def loopqueue(interaction: discord.Interaction):
    queue_data = get_queue(interaction.guild.id)
    
    queue_data['loop_queue'] = not queue_data['loop_queue']
    
    if queue_data['loop_queue']:
        queue_data['loop'] = False  # Matikan loop single jika loop queue aktif
    
    status = "🔁 **ON**" if queue_data['loop_queue'] else "🔁 **OFF**"
    await interaction.response.send_message(f"Queue loop mode: {status}")

@bot.tree.command(name="leave", description="Bot keluar dari voice channel")
async def leave(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    
    if voice_client:
        # Clear queue
        guild_id = interaction.guild.id
        if guild_id in music_queues:
            queue_data = music_queues[guild_id]
            queue_data['queue'].clear()
            queue_data['current'] = None
            queue_data['loop'] = False
            queue_data['loop_queue'] = False
        
        # Stop and disconnect
        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
        
        await voice_client.disconnect()
        await interaction.response.send_message("👋 Bot keluar dari voice channel")
    else:
        await interaction.response.send_message("❌ Bot tidak ada di voice channel", ephemeral=True)

@bot.tree.command(name="nowplaying", description="Lihat lagu yang sedang diputar")
async def nowplaying(interaction: discord.Interaction):
    queue_data = get_queue(interaction.guild.id)
    
    if queue_data['current']:
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"**{queue_data['current']['title']}**",
            color=discord.Color.green()
        )
        
        # Duration
        if queue_data['current'].get('duration'):
            minutes = queue_data['current']['duration'] // 60
            seconds = queue_data['current']['duration'] % 60
            embed.add_field(name="Duration", value=f"{minutes}:{seconds:02d}", inline=True)
        
        # Link
        if queue_data['current'].get('webpage_url'):
            embed.add_field(name="Link", value=f"[YouTube]({queue_data['current']['webpage_url']})", inline=True)
        
        # Requester
        if queue_data['current'].get('requester'):
            embed.add_field(name="Requested by", value=queue_data['current']['requester'], inline=True)
        
        # Loop status
        footer = ""
        if queue_data['loop']:
            footer += "🔁 Loop: ON (Single) "
        if queue_data['loop_queue']:
            footer += "🔁 Loop: ON (Queue) "
        
        if footer:
            embed.set_footer(text=footer.strip())
        
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("❌ Tidak ada lagu yang sedang diputar", ephemeral=True)

@bot.tree.command(name="ping", description="Cek latency bot")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latency: **{latency}ms**",
        color=discord.Color.green() if latency < 100 else discord.Color.orange()
    )
    
    # Status based on latency
    if latency < 50:
        status = "Excellent"
    elif latency < 100:
        status = "Good"
    elif latency < 200:
        status = "Fair"
    else:
        status = "Poor"
    
    embed.add_field(name="Status", value=status, inline=True)
    
    await interaction.response.send_message(embed=embed)

# ==================== RUN BOT ====================
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    print("❌ ERROR: DISCORD_TOKEN tidak ditemukan di environment variables!")
    print("ℹ️  Pastikan sudah set DISCORD_TOKEN di Railway/Heroku environment")
    
    # Coba baca dari file .env
    try:
        from dotenv import load_dotenv
        load_dotenv()
        TOKEN = os.getenv("DISCORD_TOKEN")
        if TOKEN:
            print("✓ Token ditemukan di .env file")
    except:
        pass

if TOKEN:
    print(f"✓ Token ditemukan: {TOKEN[:20]}...")
    
    # Print system info
    print("\n" + "=" * 60)
    print("SYSTEM INFORMATION")
    print("=" * 60)
    print(f"Python: {sys.version}")
    print(f"Discord.py: {discord.__version__}")
    print(f"YT-DLP: {yt_dlp.__version__}")
    print(f"FFmpeg: {'Available' if discord.ffmpeg.utils._get_ffmpeg_version() else 'Not found'}")
    print(f"Opus: {'Loaded' if discord.opus.is_loaded() else 'Not loaded'}")
    print("=" * 60 + "\n")
    
    try:
        bot.run(TOKEN, reconnect=True)
    except discord.LoginFailure:
        print("❌ ERROR: Token invalid! Pastikan token benar.")
    except Exception as e:
        print(f"❌ ERROR: {e}")
else:
    print("❌ ERROR: Tidak bisa mendapatkan DISCORD_TOKEN!")
