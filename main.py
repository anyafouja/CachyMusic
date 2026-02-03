import discord
from discord.ext import commands
import os
import subprocess
import asyncio
import youtube_dl
from collections import deque

print("=" * 60)
print("DISCORD MUSIC BOT v1.7.3 - FIXED")
print("=" * 60)

# Check FFmpeg
try:
    result = subprocess.run(['which', 'ffmpeg'], capture_output=True, text=True)
    print(f"FFmpeg: {result.stdout.strip()}")
except:
    print("FFmpeg check failed")

bot = commands.Bot(command_prefix="!", help_command=None)

# Music queue
queues = {}

# YouTube DL options
ytdl_format_options = {
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
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        
        if 'entries' in data:
            data = data['entries'][0]
        
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

def get_queue(guild_id):
    if guild_id not in queues:
        queues[guild_id] = deque()
    return queues[guild_id]

@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')
    print(f'Bot ID: {bot.user.id}')
    print(f'Connected to {len(bot.guilds)} guild(s)')
    print('=' * 60)
    
    await bot.change_presence(activity=discord.Game(name="!play | Music Bot"))

async def play_next(ctx):
    voice_client = ctx.voice_client
    queue = get_queue(ctx.guild.id)
    
    if not voice_client or not queue:
        return
    
    try:
        url = queue[0]
        player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
        
        def after_playing(error):
            if error:
                print(f'Player error: {error}')
            
            # Remove from queue
            if queue:
                queue.popleft()
            
            # Play next if still connected
            if voice_client.is_connected() and queue:
                asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
        
        voice_client.play(player, after=after_playing)
        await ctx.send(f'Now playing: **{player.title}**')
        
    except Exception as e:
        print(f'Error in play_next: {e}')
        if queue:
            queue.popleft()
        await play_next(ctx)

@bot.command()
async def join(ctx):
    """Join your voice channel"""
    if not ctx.author.voice:
        await ctx.send("You are not connected to a voice channel.")
        return
    
    channel = ctx.author.voice.channel
    await channel.connect()
    await ctx.send(f'Joined {channel.name}')

@bot.command()
async def play(ctx, *, url):
    """Play music from YouTube"""
    if not ctx.author.voice:
        await ctx.send("You are not connected to a voice channel.")
        return
    
    voice_client = ctx.voice_client
    
    # Connect if not connected
    if not voice_client:
        try:
            voice_client = await ctx.author.voice.channel.connect()
        except Exception as e:
            await ctx.send(f"Could not connect to voice channel: {e}")
            return
    
    try:
        # Add to queue
        queue = get_queue(ctx.guild.id)
        
        # If URL doesn't start with http, treat as search
        if not url.startswith(('http://', 'https://')):
            url = f"ytsearch:{url}"
        
        queue.append(url)
        
        # If not playing, start playback
        if not voice_client.is_playing():
            await play_next(ctx)
        else:
            # Try to get title
            try:
                data = await bot.loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
                if 'entries' in data:
                    data = data['entries'][0]
                title = data.get('title', url)
                await ctx.send(f'Added to queue: **{title}** (Position: {len(queue)})')
            except:
                await ctx.send(f'Added to queue: {url} (Position: {len(queue)})')
        
    except Exception as e:
        await ctx.send(f'Error: {str(e)[:150]}')

@bot.command()
async def pause(ctx):
    """Pause the music"""
    voice_client = ctx.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await ctx.send('Paused')
    else:
        await ctx.send('Not playing any music.')

@bot.command()
async def resume(ctx):
    """Resume the music"""
    voice_client = ctx.voice_client
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await ctx.send('Resumed')
    else:
        await ctx.send('Music is not paused.')

@bot.command()
async def stop(ctx):
    """Stop the music"""
    voice_client = ctx.voice_client
    if voice_client:
        # Clear queue
        if ctx.guild.id in queues:
            queues[ctx.guild.id].clear()
        
        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
        
        await ctx.send('Stopped and queue cleared')
    else:
        await ctx.send('Not in a voice channel.')

@bot.command()
async def skip(ctx):
    """Skip current song"""
    voice_client = ctx.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await ctx.send('Skipped')
    else:
        await ctx.send('Not playing any music.')

@bot.command()
async def queue(ctx):
    """Show the queue"""
    queue_list = get_queue(ctx.guild.id)
    
    if not queue_list:
        await ctx.send('Queue is empty.')
        return
    
    message = '**Music Queue:**\n'
    for i, url in enumerate(list(queue_list)[:10], 1):
        try:
            # Get title for display
            data = await bot.loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False, process=False))
            if 'entries' in data:
                data = data['entries'][0]
            title = data.get('title', 'Unknown')
            message += f'{i}. {title}\n'
        except:
            message += f'{i}. {url}\n'
    
    if len(queue_list) > 10:
        message += f'\n...and {len(queue_list) - 10} more'
    
    await ctx.send(message)

@bot.command()
async def leave(ctx):
    """Leave voice channel"""
    voice_client = ctx.voice_client
    if voice_client:
        # Clear queue
        if ctx.guild.id in queues:
            queues[ctx.guild.id].clear()
        
        await voice_client.disconnect()
        await ctx.send('Left voice channel')
    else:
        await ctx.send('Not in a voice channel.')

@bot.command()
async def ping(ctx):
    """Check bot latency"""
    latency = round(bot.latency * 1000)
    await ctx.send(f'Pong! {latency}ms')

@bot.command()
async def test(ctx):
    """Test command"""
    await ctx.send('Bot is working!')

@bot.command()
async def say(ctx, *, message: str):
    """Make the bot say something"""
    await ctx.send(message)

# Error handling
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send('Missing required argument.')
    else:
        print(f'Error: {error}')
        await ctx.send(f'An error occurred: {str(error)[:100]}')

# Run bot
TOKEN = os.getenv('DISCORD_TOKEN')

if TOKEN:
    print(f"Token found: {TOKEN[:20]}...")
    print("Starting bot...")
    print('=' * 60)
    bot.run(TOKEN)
else:
    print("ERROR: No DISCORD_TOKEN found!")
    print("Make sure to set DISCORD_TOKEN environment variable")
