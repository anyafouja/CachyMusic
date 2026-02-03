import discord
from discord.ext import commands
import os
import subprocess
import asyncio
import yt_dlp

print("=" * 60)
print("DISCORD MUSIC BOT - FIXED VERSION")
print("=" * 60)

# Check FFmpeg
print("Checking FFmpeg...")
result = subprocess.run(['which', 'ffmpeg'], capture_output=True, text=True)
print(f"FFmpeg: {result.stdout.strip() or 'NOT FOUND'}")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# YTDL Setup
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'noplaylist': True,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -filter:a "volume=0.5"'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

@bot.event
async def on_ready():
    print(f"Bot {bot.user} online!")
    print(f"Guilds: {len(bot.guilds)}")
    
    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"Sync error: {e}")
    
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="/play"))

# ========== HYBRID COMMANDS (BOTH ! AND /) ==========

@bot.hybrid_command(name="play", description="Play music from YouTube")
async def play(ctx, *, query: str):
    """Play music from YouTube (use !play or /play)"""
    await ctx.defer()
    
    if not ctx.author.voice:
        await ctx.send("Join voice channel first!", ephemeral=True)
        return
    
    try:
        # Connect to voice
        if not ctx.voice_client:
            vc = await ctx.author.voice.channel.connect()
        elif ctx.voice_client.channel != ctx.author.voice.channel:
            vc = await ctx.voice_client.move_to(ctx.author.voice.channel)
        else:
            vc = ctx.voice_client
        
        # Get audio info
        info = ytdl.extract_info(query, download=False)
        if 'entries' in info:
            info = info['entries'][0]
        
        audio_url = info['url']
        title = info.get('title', 'Unknown')
        
        # Play audio
        source = discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS)
        
        def after_playing(error):
            if error:
                print(f"Playback error: {error}")
        
        vc.play(source, after=after_playing)
        
        await ctx.send(f"Now playing: **{title}**")
        
    except Exception as e:
        await ctx.send(f"Error: {str(e)[:150]}")

@bot.hybrid_command(name="join", description="Join voice channel")
async def join(ctx):
    """Join your voice channel"""
    if not ctx.author.voice:
        await ctx.send("You're not in a voice channel!", ephemeral=True)
        return
    
    try:
        vc = await ctx.author.voice.channel.connect()
        await ctx.send(f"Joined {vc.channel.name}")
    except Exception as e:
        await ctx.send(f"Error: {str(e)}")

@bot.hybrid_command(name="leave", description="Leave voice channel")
async def leave(ctx):
    """Leave voice channel"""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Left voice channel")
    else:
        await ctx.send("Not in a voice channel", ephemeral=True)

@bot.hybrid_command(name="pause", description="Pause current music")
async def pause(ctx):
    """Pause music"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("Music paused")
    else:
        await ctx.send("No music playing", ephemeral=True)

@bot.hybrid_command(name="resume", description="Resume paused music")
async def resume(ctx):
    """Resume music"""
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("Music resumed")
    else:
        await ctx.send("Music not paused", ephemeral=True)

@bot.hybrid_command(name="skip", description="Skip current song")
async def skip(ctx):
    """Skip song"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("Skipped")
    else:
        await ctx.send("No music playing", ephemeral=True)

@bot.hybrid_command(name="stop", description="Stop music and clear queue")
async def stop(ctx):
    """Stop music"""
    if ctx.voice_client:
        if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
            ctx.voice_client.stop()
        await ctx.send("Music stopped")
    else:
        await ctx.send("Not in voice channel", ephemeral=True)

@bot.hybrid_command(name="ping", description="Check bot latency")
async def ping(ctx):
    """Check latency"""
    latency = round(bot.latency * 1000)
    await ctx.send(f"Pong! {latency}ms")

# ========== NORMAL PREFIX COMMANDS ==========

@bot.command()
async def test(ctx):
    """Test command"""
    await ctx.send("Bot is working!")

@bot.command()
async def say(ctx, *, message: str):
    """Repeat message"""
    await ctx.send(message)

# ========== RUN BOT ==========

TOKEN = os.getenv("DISCORD_TOKEN")

if TOKEN:
    print(f"Token found: {TOKEN[:20]}...")
    print("Starting bot...")
    bot.run(TOKEN)
else:
    print("ERROR: No token found!")
