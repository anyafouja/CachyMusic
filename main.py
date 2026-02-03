import discord
from discord.ext import commands
import os
import subprocess
import asyncio

print("=" * 60)
print("DISCORD MUSIC BOT - RAILWAY FIX")
print("=" * 60)

# Check system
print("Checking system...")
print(f"Python: {os.sys.version}")
print(f"Current dir: {os.getcwd()}")
print(f"Files in dir: {os.listdir('.')}")

# Try to install ffmpeg via apt
print("\nInstalling ffmpeg...")
try:
    subprocess.run(['apt-get', 'update'], check=False)
    subprocess.run(['apt-get', 'install', '-y', 'ffmpeg'], check=False)
    
    # Check if installed
    result = subprocess.run(['which', 'ffmpeg'], capture_output=True, text=True)
    if result.stdout:
        print(f"FFmpeg found at: {result.stdout.strip()}")
    else:
        print("FFmpeg not found after installation")
except Exception as e:
    print(f"Install error: {e}")

print("=" * 60)

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot {bot.user} online!")
    print(f"Guilds: {len(bot.guilds)}")
    
    # Test voice connection capability
    print("\nTesting voice capabilities...")
    try:
        # This will show if opus is loaded
        import discord.opus
        print(f"Opus loaded: {discord.opus.is_loaded()}")
    except:
        print("Opus not available")

@bot.command()
async def join(ctx):
    """Simple join command"""
    if not ctx.author.voice:
        await ctx.send("Join voice channel first!")
        return
    
    try:
        vc = await ctx.author.voice.channel.connect()
        await ctx.send(f"Connected to {vc.channel.name}")
        
        # Try to play simple audio
        await play_test_audio(ctx, vc)
        
    except Exception as e:
        await ctx.send(f"Error: {str(e)[:150]}")

async def play_test_audio(ctx, vc):
    """Try different audio methods"""
    methods = [
        # Method 1: Raw PCM
        lambda: discord.FFmpegPCMAudio(
            'pipe:0',
            before_options='-f lavfi -i sine=frequency=440:duration=1',
            options='-f s16le -ar 48000 -ac 2'
        ),
        # Method 2: Direct file (silent)
        lambda: discord.FFmpegPCMAudio(
            'pipe:0',
            before_options='-f lavfi -i anullsrc=channel_layout=stereo:sample_rate=48000:duration=1',
            options='-f s16le'
        )
    ]
    
    for i, method in enumerate(methods):
        try:
            source = method()
            vc.play(source)
            
            # Wait for playback
            while vc.is_playing():
                await asyncio.sleep(0.1)
            
            await ctx.send(f"Audio test {i+1} passed")
            await asyncio.sleep(0.5)
            
        except Exception as e:
            await ctx.send(f"Test {i+1} failed: {str(e)[:100]}")

@bot.command()
async def play(ctx, url: str = None):
    """Play music from YouTube"""
    if not ctx.author.voice:
        await ctx.send("Join voice channel first!")
        return
    
    if not url:
        await ctx.send("Please provide a URL or search term")
        return
    
    try:
        # Connect if not connected
        if not ctx.voice_client:
            vc = await ctx.author.voice.channel.connect()
        else:
            vc = ctx.voice_client
        
        await ctx.send(f"Processing: {url[:50]}...")
        
        # Use yt-dlp to get audio
        import yt_dlp
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'default_search': 'ytsearch',
            'noplaylist': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if 'entries' in info:
                info = info['entries'][0]
            
            audio_url = info['url']
            title = info.get('title', 'Unknown')
            
            # Play with FFmpeg
            ffmpeg_options = {
                'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                'options': '-vn -filter:a "volume=0.5"'
            }
            
            source = discord.FFmpegPCMAudio(audio_url, **ffmpeg_options)
            vc.play(source)
            
            await ctx.send(f"Now playing: {title}")
            
    except Exception as e:
        await ctx.send(f"Error: {str(e)[:150]}")

@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Disconnected")
    else:
        await ctx.send("Not in voice channel")

@bot.command()
async def ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f"Latency: {latency}ms")

TOKEN = os.getenv("DISCORD_TOKEN")

if TOKEN:
    print(f"\nToken found: {TOKEN[:20]}...")
    print("Starting bot...")
    bot.run(TOKEN)
else:
    print("ERROR: No token found!")
