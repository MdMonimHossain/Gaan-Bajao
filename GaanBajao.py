import os
import asyncio
import json
import discord
from discord.ext import commands, tasks
import yt_dlp
from youtube_search import YoutubeSearch
from pathlib import Path

song_queue = {}

ydl_opts = {
    'format': 'bestaudio/best',
    'outtmpl': '%(id)s.mp3',
    'postprocessors':
        [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
}

client = commands.Bot(command_prefix='=')


def download(song_info):
    video_url = 'https://www.youtube.com/watch?v=' + song_info['id']
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        download_err = ydl.download([video_url])
        return download_err


def get_song_data(key_word):
    results = YoutubeSearch(key_word, max_results=1).to_json()
    json_data = json.loads(results)
    song_info = json_data['videos'][0]
    return song_info


@client.event
async def on_ready():
    print(f'{client.user} is online.')
    await client.change_presence(
        activity=discord.Activity(type=discord.ActivityType.listening, name='Type "=help" For Help'))


async def join(ctx):
    global song_queue
    guild_id = ctx.message.guild.id
    if guild_id not in song_queue:
        song_queue[guild_id] = []
        
    if not ctx.message.author.voice:
        await ctx.send("**You are not connected to a voice channel**")
        return None

    channel = ctx.message.author.voice.channel
    voice = ctx.message.guild.voice_client
    
    if voice:
        if (not voice.is_connected()) or (channel is not voice.channel):
            song_queue[guild_id] = []
            await voice.disconnect(force=True)
            voice = await channel.connect(timeout=30.0, reconnect=False)
    else:
        song_queue[guild_id] = []
        voice = await channel.connect(timeout=30.0, reconnect=False)
    
    return voice


@client.command(name='leave', help='Leaves the voice channel')
async def leave(ctx):
    global song_queue
    guild_id = ctx.message.guild.id
    song_queue[guild_id] = []

    voice = ctx.message.guild.voice_client
    if voice and voice.is_connected():
        await voice.disconnect()
    await ctx.message.add_reaction('\u2705')


@client.command(name='p', help='"=p SongName" plays the song')
async def play(ctx):
    global song_queue
    guild_id = ctx.message.guild.id
    voice = await join(ctx)
    if voice is None:
        return
    
    try:
        key_word = ctx.message.content.split("=p ", 1)[1]
    except IndexError:
        await ctx.send('**Type "=p SongName" to play the song**')
        return
    song_info = get_song_data(key_word)
    title = song_info['title']
    song_id = song_info['id']
    song_queue[guild_id].append(song_id)

    if voice.is_playing() or voice.is_paused():
        async with ctx.typing():
            if not Path(song_id + '.mp3').is_file():
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, download, song_info)
            else:
                print(song_id + '.mp3 already exists')
        await ctx.send('**Queued to play next:** ' + title)
        await ctx.message.add_reaction('\u25B6')
        return

    try:
        song_queue[guild_id].pop(0)
        async with ctx.typing():
            if not Path(song_id + '.mp3').is_file():
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, download, song_info)
            else:
                print(song_id + '.mp3 already exists')
            voice.play(discord.FFmpegPCMAudio(song_id + '.mp3'),
                       after=lambda e: play_next_song(ctx))

        await ctx.send(f'**Now playing:** {title}')
        await ctx.message.add_reaction('\u25B6')
    except Exception as e:
        await ctx.send('**Sorry! Error occured playing the song**')
        print(e)


def play_next_song(ctx, in_loop=False):
    global song_queue
    guild_id = ctx.message.guild.id
    voice = ctx.message.guild.voice_client

    if voice and len(song_queue) != 0 and song_queue[guild_id] != []:
        try:
            if in_loop and len(song_queue[guild_id]) > 1:
                song_id = song_queue[guild_id][1]
            else:
                song_id = song_queue[guild_id][0]
            if not in_loop or len(song_queue[guild_id]) > 1:
                song_queue[guild_id].pop(0)
                
            if not Path(song_id + '.mp3').is_file():
                download({'id': song_id})
            else:
                print(song_id + '.mp3 already exists')
            voice.play(discord.FFmpegPCMAudio(song_id + '.mp3'),
                       after=lambda e: play_next_song(ctx, in_loop))

        except Exception as e:
            print(e)

    else:
        print(f'queue is empty for {ctx.message.guild.name}')


@client.command(name='skip', help='Skips current song and plays next song in queue')
async def skip(ctx):
    voice = ctx.message.guild.voice_client
    if voice:
        voice.stop()

        async with ctx.typing():
            await ctx.send('**Skipped!**')
            await ctx.message.add_reaction('\u2705')


@client.command(name='loop', help='"=loop SongName" loops the song')
async def loop_song(ctx):
    global song_queue
    guild_id = ctx.message.guild.id
    song_queue[guild_id] = []
    voice = await join(ctx)
    if voice is None:
        return
    if voice.is_playing() or voice.is_paused():
        voice.stop()

    try:
        key_word = ctx.message.content.split("=loop ", 1)[1]
    except IndexError:
        await ctx.send('**Type "=loop SongName" to play the song in loop**')
        return
    song_info = get_song_data(key_word)
    title = song_info['title']
    song_id = song_info['id']
    song_queue[guild_id] = [song_id]

    try:
        async with ctx.typing():
            if not Path(song_id + '.mp3').is_file():
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, download, song_info)
            else:
                print(song_id + '.mp3 already exists')
            voice.play(discord.FFmpegPCMAudio(song_id + '.mp3'),
                       after=lambda e: play_next_song(ctx, True))

        await ctx.send(f'**Playing in loop:** {title}')
        await ctx.message.add_reaction('🔂')
    except Exception as e:
        await ctx.send('**Sorry! Error occured playing the song**')
        print(e)


@client.command(name='pause', help='Pauses current song')
async def pause(ctx):
    voice = ctx.message.guild.voice_client
    if voice:
        voice.pause()
        await ctx.message.add_reaction('\u23F8')


@client.command(name='resume', help='Resumes current song')
async def resume(ctx):
    voice = ctx.message.guild.voice_client
    if voice:
        voice.resume()
        await ctx.message.add_reaction('\u25B6')


@client.command(name='stop', help='Stops playing song')
async def stop(ctx):
    global song_queue
    guild_id = ctx.message.guild.id
    song_queue[guild_id] = []

    voice = ctx.message.guild.voice_client
    if voice:
        voice.stop()
        await ctx.message.add_reaction('\u23F9')


@client.command(name='queue', help='Shows the queue')
async def view_queue(ctx):
    global song_queue
    song_count = 1
    guild_id = ctx.message.guild.id
    if guild_id in song_queue:
        song_list = ''
        for song_id in song_queue[guild_id]:
            song_list = song_list + '**' + str(song_count) + '.** ' + 'https://www.youtube.com/watch?v=' + song_id + '\n'
            song_count += 1;
        if song_list:
            await ctx.send(song_list)
        else:
            await ctx.send('**No song in queue!**')
        await ctx.message.add_reaction('\u2705')


client.run(os.environ.get('TOKEN'))
