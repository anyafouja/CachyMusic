import discord
from discord.ext import commands
import os
import subprocess

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
        print("✓ FFmpeg is installed and working!")
        print(f"Version: {version_result.stdout.split('\\n')[0]}")
    else:
        print("✗ FFmpeg is not working")
except Exception as e:
    print(f"✗ FFmpeg test failed: {e}")

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
    """Join voice channel"""
    if not ctx.author.voice:
        await ctx.send("You need to be in a voice channel!")
        return
    
    channel = ctx.author.voice.channel
    
    try:
        vc = await channel.connect()
        await ctx.send(f"✅ Connected to {channel.name}")
        
        # Test FFmpeg di voice channel
        await test_ffmpeg(ctx, vc)
        
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

async def test_ffmpeg(ctx, vc):
    """Test FFmpeg dengan audio dummy"""
    try:
        # Method 1: Generate silent audio dengan FFmpeg
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn -f s16le -ar 48000 -ac 2'
        }
        
        # Coba beberapa metode berbeda
        audio_sources = [
            # Method 1: Dummy audio dari FFmpeg
            discord.FFmpegPCMAudio(
                "pipe:0",
                before_options='-f lavfi -i anullsrc=r=48000:cl=stereo -t 3',
                options='-f s16le -acodec pcm_s16le'
            ),
            # Method 2: Simple PCM
            discord.FFmpegPCMAudio(
                "pipe:0",
                before_options='-f lavfi -i sine=frequency=1000:duration=2',
                options='-f s16le -acodec pcm_s16le'
            )
        ]
        
        for i, source in enumerate(audio_sources):
            try:
                vc.play(source)
                await ctx.send(f"🎵 Playing test audio {i+1}...")
                
                # Tunggu sampai selesai
                while vc.is_playing():
                    await asyncio.sleep(0.1)
                    
                await asyncio.sleep(1)
                
            except Exception as e:
                await ctx.send(f"Audio test {i+1} failed: {str(e)[:100]}")
        
        await ctx.send("✅ All audio tests completed!")
        
    except Exception as e:
        await ctx.send(f"❌ Audio test failed: {str(e)}")

@bot.command()
async def leave(ctx):
    """Leave voice channel"""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("✅ Left voice channel")
    else:
        await ctx.send("❌ Not in a voice channel")

@bot.command()
async def ping(ctx):
    """Check bot latency"""
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! Latency: {latency}ms")

TOKEN = os.getenv("DISCORD_TOKEN")

if TOKEN:
    print(f"Token found: {TOKEN[:20]}...")
    print("Starting bot...")
    bot.run(TOKEN)
else:
    print("❌ ERROR: No DISCORD_TOKEN found!")
