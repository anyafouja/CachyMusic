import discord
from discord.ext import commands
import os
import subprocess
import asyncio

print("=" * 60)
print("TESTING FFMPEG BOT")
print("=" * 60)

# Test FFmpeg
print("Testing FFmpeg installation...")
try:
    result = subprocess.run(['which', 'ffmpeg'], capture_output=True, text=True)
    print(f"FFmpeg path: {result.stdout.strip()}")
    
    version_result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
    if version_result.returncode == 0:
        print("FFmpeg is installed and working!")
        # FIX: jangan pakai backslash di f-string
        first_line = version_result.stdout.split('\n')[0]
        print(f"Version: {first_line}")
    else:
        print("FFmpeg is not working")
except Exception as e:
    print(f"FFmpeg test failed: {e}")

print("=" * 60)

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot {bot.user} is ready!")
    print(f"Connected to {len(bot.guilds)} guild(s)")
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="!join to test"
        )
    )

@bot.command()
async def join(ctx):
    if not ctx.author.voice:
        await ctx.send("You need to be in a voice channel!")
        return
    
    channel = ctx.author.voice.channel
    
    try:
        vc = await channel.connect()
        await ctx.send(f"Connected to {channel.name}")
        
        await test_ffmpeg(ctx, vc)
        
    except Exception as e:
        await ctx.send(f"Error: {str(e)}")

async def test_ffmpeg(ctx, vc):
    try:
        # Test dengan audio sederhana
        await ctx.send("Testing audio playback...")
        
        # Method 1: Audio test sederhana
        try:
            audio_source = discord.FFmpegPCMAudio(
                "pipe:0",
                before_options='-f lavfi -i sine=frequency=1000:duration=2',
                options='-f s16le -acodec pcm_s16le'
            )
            
            vc.play(audio_source)
            
            # Tunggu selesai
            while vc.is_playing():
                await asyncio.sleep(0.1)
                
            await ctx.send("Audio test 1 passed")
            
        except Exception as e:
            await ctx.send(f"Audio test 1 failed: {str(e)[:100]}")
        
        # Test kedua
        await asyncio.sleep(1)
        
        try:
            # Test dengan opsi berbeda
            audio_source2 = discord.FFmpegPCMAudio(
                "pipe:0",
                before_options='-f lavfi -i anullsrc=r=48000:cl=stereo -t 2',
                options='-f s16le -acodec pcm_s16le'
            )
            
            vc.play(audio_source2)
            
            while vc.is_playing():
                await asyncio.sleep(0.1)
                
            await ctx.send("Audio test 2 passed")
            
        except Exception as e:
            await ctx.send(f"Audio test 2 failed: {str(e)[:100]}")
        
        await ctx.send("All audio tests completed")
        
    except Exception as e:
        await ctx.send(f"Audio test failed: {str(e)}")

@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Left voice channel")
    else:
        await ctx.send("Not in a voice channel")

@bot.command()
async def ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f"Pong! Latency: {latency}ms")

@bot.command()
async def playtest(ctx, url: str = None):
    if not ctx.author.voice:
        await ctx.send("Join voice channel first!")
        return
    
    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()
    
    vc = ctx.voice_client
    
    try:
        if url:
            # Simple audio from URL
            await ctx.send(f"Testing audio from: {url[:50]}")
            
            # Pakai yt-dlp sederhana
            import yt_dlp
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'quiet': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                audio_url = info['url']
                
                audio_source = discord.FFmpegPCMAudio(
                    audio_url,
                    before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                    options='-vn'
                )
                
                vc.play(audio_source)
                await ctx.send("Playing audio from URL...")
        else:
            # Default test
            await test_ffmpeg(ctx, vc)
            
    except Exception as e:
        await ctx.send(f"Playtest error: {str(e)[:150]}")

TOKEN = os.getenv("DISCORD_TOKEN")

if TOKEN:
    print(f"Token found: {TOKEN[:20]}...")
    print("Starting bot...")
    bot.run(TOKEN)
else:
    print("ERROR: No DISCORD_TOKEN found!")
