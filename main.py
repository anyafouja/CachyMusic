import discord
from discord.ext import commands
import os
import subprocess
import asyncio
import yt_dlp
from collections import deque

print("=" * 60)
print("DISCORD MUSIC BOT - WITH PYNACL FIX")
print("=" * 60)

# Check system
print("Checking system...")
result = subprocess.run(['which', 'ffmpeg'], capture_output=True, text=True)
print(f"FFmpeg: {result.stdout.strip() or 'NOT FOUND'}")

# Check PyNaCl
try:
    import nacl
    print(f"PyNaCl version: {nacl.__version__}")
except:
    print("PyNaCl not imported properly")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Music queue
music_queues = {}

# YTDL Setup
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'noplaylist': True,
    'extract_flat': False,
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
    
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening, 
        name="/play | !play"
    ))

def get_queue(guild_id):
    if guild_id not in music_queues:
        music_queues[guild_id] = deque()
    return music_queues[guild_id]

async def play_next(ctx):
    """Play next song in queue"""
    if not ctx.voice_client or not ctx.voice_client.is_connected():
        return
    
    queue = get_queue(ctx.guild.id)
    
    if not queue:
        return
    
    try:
        # Get next song
        song_url = queue[0]
        
        # Get audio info
        info = ytdl.extract_info(song_url, download=False)
        if 'entries' in info:
            info = info['entries'][0]
        
        audio_url = info['url']
        title = info.get('title', 'Unknown')
        
        # Play audio
        source = discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS)
        
        def after_playing(error):
            if error:
                print(f"Playback error: {error}")
            
            # Remove from queue and play next
            queue = get_queue(ctx.guild.id)
            if queue:
                queue.popleft()
            
            # Play next if still connected
            if ctx.voice_client and ctx.voice_client.is_connected():
                asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
        
        ctx.voice_client.play(source, after=after_playing)
        
        # Send playing message
        channel = ctx.channel
        await channel.send(f"Now playing: **{title}**")
        
    except Exception as e:
        print(f"Error in play_next: {e}")
        # Remove failed song and try next
        queue = get_queue(ctx.guild.id)
        if queue:
            queue.popleft()
        await play_next(ctx)

# ========== HYBRID COMMANDS ==========

@bot.hybrid_command(name="play", description="Play music from YouTube")
async def play(ctx, *, query: str):
    """Play music from YouTube"""
    await ctx.defer()
    
    if not ctx.author.voice:
        await ctx.send("Join voice channel first!", ephemeral=True)
        return
    
    try:
        # Connect to voice
        if not ctx.voice_client:
            vc = await ctx.author.voice.channel.connect()
            print(f"Connected to {vc.channel.name}")
        elif ctx.voice_client.channel != ctx.author.voice.channel:
            vc = await ctx.voice_client.move_to(ctx.author.voice.channel)
            print(f"Moved to {vc.channel.name}")
        else:
            vc = ctx.voice_client
        
        # Get audio info
        print(f"Searching for: {query}")
        info = ytdl.extract_info(query, download=False)
        
        if 'entries' in info:
            info = info['entries'][0]
        
        audio_url = info['url']
        title = info.get('title', 'Unknown')
        webpage_url = info.get('webpage_url', audio_url)
        
        # Add to queue
        queue = get_queue(ctx.guild.id)
        queue.append(webpage_url)
        
        # If not playing, start playback
        if not vc.is_playing() and not vc.is_paused():
            await play_next(ctx)
            await ctx.send(f"Now playing: **{title}**")
        else:
            await ctx.send(f"Added to queue: **{title}** (Position: {len(queue)})")
        
    except Exception as e:
        print(f"Error in play command: {e}")
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
        # Clear queue
        if ctx.guild.id in music_queues:
            music_queues[ctx.guild.id].clear()
        
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
        # Clear queue
        if ctx.guild.id in music_queues:
            music_queues[ctx.guild.id].clear()
        
        if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
            ctx.voice_client.stop()
        
        await ctx.send("Music stopped and queue cleared")
    else:
        await ctx.send("Not in voice channel", ephemeral=True)

@bot.hybrid_command(name="queue", description="Show music queue")
async def queue_cmd(ctx):
    """Show queue"""
    queue = get_queue(ctx.guild.id)
    
    if not queue:
        await ctx.send("Queue is empty")
        return
    
    message = "**Music Queue:**\n"
    for i, song_url in enumerate(list(queue)[:10], 1):
        try:
            info = ytdl.extract_info(song_url, download=False, process=False)
            if 'entries' in info:
                info = info['entries'][0]
            title = info.get('title', 'Unknown')
            message += f"{i}. {title}\n"
        except:
            message += f"{i}. Unknown\n"
    
    if len(queue) > 10:
        message += f"\n...and {len(queue) - 10} more"
    
    await ctx.send(message)

@bot.hybrid_command(name="nowplaying", description="Show currently playing song")
async def nowplaying(ctx):
    """Show now playing"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        queue = get_queue(ctx.guild.id)
        if queue:
            try:
                song_url = queue[0]
                info = ytdl.extract_info(song_url, download=False, process=False)
                if 'entries' in info:
                    info = info['entries'][0]
                title = info.get('title', 'Unknown')
                await ctx.send(f"Now playing: **{title}**")
            except:
                await ctx.send("Now playing: Unknown")
        else:
            await ctx.send("Nothing is playing")
    else:
        await ctx.send("No music is playing", ephemeral=True)

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
