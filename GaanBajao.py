import os
from dotenv import load_dotenv
import asyncio
import json
from discord import Activity, ActivityType, Intents, FFmpegPCMAudio
from discord.ext import commands, tasks
from yt_dlp import YoutubeDL
from youtube_search import YoutubeSearch
import numpy as np


SONGS_PATH = './.songs_cache/'

ffmpeg_processes = {}
song_queue = {}
songs = np.empty(0, dtype=str)

ydl_opts = {
    'format': 'bestaudio/best',
    'outtmpl': SONGS_PATH + '%(id)s',
    'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
}

bot = commands.Bot(intents=Intents.all(), command_prefix='=')


def download_song(song_id: str):
    global songs
    if song_id in songs:
        return

    video_url = 'https://www.youtube.com/watch?v=' + song_id
    with YoutubeDL(ydl_opts) as ydl:
        error_code = ydl.download([video_url])
        if error_code == 0:
            songs = np.append(songs, song_id)


def get_song_info(keyword):
    result = YoutubeSearch(keyword, max_results=1).to_json()
    json_data = json.loads(result)
    return json_data['videos'][0]


# not sure if this is the right way to do it
def cleanup_ffmpeg_process(ctx: commands.Context, all=False):
    global ffmpeg_processes
    guild_id = ctx.guild.id
    if guild_id in ffmpeg_processes:
        if all:
            for process in ffmpeg_processes[guild_id]:
                process.cleanup()
            ffmpeg_processes[guild_id] = []
        else:
            ffmpeg_processes[guild_id][0].cleanup()
            ffmpeg_processes[guild_id].pop(0)


@bot.event
async def on_ready():
    print(f'{bot.user} is online.')
    afk_disconnect.start()
    clear_cache.start()
    await bot.change_presence(activity=Activity(type=ActivityType.listening, name='Type =help For Help'))


async def disconnect_bot(ctx: commands.Context):
    cleanup_ffmpeg_process(ctx, all=True)
    voice_client = ctx.voice_client
    if voice_client.is_connected():
        song_queue[ctx.guild.id] = []
        await voice_client.disconnect()


async def connect_bot(ctx: commands.Context):
    global song_queue
    guild_id = ctx.guild.id

    if not ctx.author.voice:
        await ctx.send("**You are not connected to a voice channel**")
        return None

    author_channel = ctx.author.voice.channel
    guild_voice_client = ctx.voice_client

    if guild_voice_client in ctx.bot.voice_clients:
        if guild_voice_client.channel == author_channel:
            return guild_voice_client
        await disconnect_bot(ctx)

    song_queue[guild_id] = []
    ffmpeg_processes[guild_id] = []
    return await author_channel.connect()


@bot.command(name='leave', help='Leaves the voice channel')
async def leave(ctx: commands.Context):
    await disconnect_bot(ctx)
    await ctx.message.add_reaction('\u2705')


@bot.command(name='p', help='"=p SongName" plays the song')
async def play(ctx):
    global song_queue
    guild_id = ctx.guild.id
    voice_client = await connect_bot(ctx)
    if voice_client is None:
        return

    try:
        keyword = ctx.message.content.split("=p ", 1)[1]
    except IndexError:
        await ctx.send('**Type "=p SongName" to play the song**')
        return

    song_info = get_song_info(keyword)
    song_title = song_info['title']
    song_id = song_info['id']
    song_queue[guild_id].append(song_id)

    if voice_client.is_playing() or voice_client.is_paused():
        async with ctx.typing():
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, download_song, song_id)

        await ctx.send('**Queued to play next:** ' + song_title)
        await ctx.message.add_reaction('\u25B6')
        return

    try:
        song_queue[guild_id].pop(0)
        async with ctx.typing():
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, download_song, song_id)

            faudio: FFmpegPCMAudio = FFmpegPCMAudio(
                SONGS_PATH + song_id + '.mp3')
            ffmpeg_processes[guild_id].append(faudio)
            voice_client.play(faudio, after=lambda e: play_next_song(ctx))

        await ctx.send(f'**Now playing:** {song_title}')
        await ctx.message.add_reaction('\u25B6')
    except Exception as e:
        await ctx.send('**Sorry! Error occured playing the song**')
        print(e)


def play_next_song(ctx: commands.Context, in_loop=False):
    global song_queue
    guild_id = ctx.guild.id
    voice_client = ctx.voice_client

    if voice_client.is_connected() and song_queue.get(guild_id):
        try:
            if in_loop and len(song_queue[guild_id]) > 1:
                song_id = song_queue[guild_id][1]
            else:
                song_id = song_queue[guild_id][0]
            if not in_loop or len(song_queue[guild_id]) > 1:
                song_queue[guild_id].pop(0)

            download_song(song_id)
            faudio: FFmpegPCMAudio = FFmpegPCMAudio(
                SONGS_PATH + song_id + '.mp3')
            ffmpeg_processes[guild_id].append(faudio)
            voice_client.play(
                faudio, after=lambda e: play_next_song(ctx, in_loop))

        except Exception as e:
            print(e)


@bot.command(name='skip', help='Skips current song and plays next song in queue')
async def skip(ctx: commands.Context):
    voice_client = ctx.voice_client

    if voice_client.is_connected() and (voice_client.is_playing() or voice_client.is_paused()):
        cleanup_ffmpeg_process(ctx)
        voice_client.stop()

        async with ctx.typing():
            await ctx.send('**Skipped!**')
            await ctx.message.add_reaction('\u2705')


@bot.command(name='loop', help='"=loop SongName" loops the song')
async def loop_song(ctx: commands.Context):
    global song_queue
    guild_id = ctx.guild.id
    voice_client = await connect_bot(ctx)
    if voice_client is None:
        return
    if voice_client.is_playing() or voice_client.is_paused():
        cleanup_ffmpeg_process(ctx)
        voice_client.stop()

    try:
        keyword = ctx.message.content.split("=loop ", 1)[1]
    except IndexError:
        await ctx.send('**Type "=loop SongName" to play the song in loop**')
        return

    song_info = get_song_info(keyword)
    song_title = song_info['title']
    song_id = song_info['id']
    song_queue[guild_id] = [song_id]

    try:
        async with ctx.typing():
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, download_song, song_id)

            faudio: FFmpegPCMAudio = FFmpegPCMAudio(
                SONGS_PATH + song_id + '.mp3')
            ffmpeg_processes[guild_id].append(faudio)
            voice_client.play(
                faudio, after=lambda e: play_next_song(ctx, in_loop=True))

        await ctx.send(f'**Playing in loop:** {song_title}')
        await ctx.message.add_reaction('🔂')
    except Exception as e:
        await ctx.send('**Sorry! Error occured playing the song**')
        print(e)


@bot.command(name='pause', help='Pauses current song')
async def pause(ctx: commands.Context):
    voice_client = ctx.guild.voice_client
    if voice_client.is_connected() and voice_client.is_playing():
        voice_client.pause()
        await ctx.message.add_reaction('\u23F8')


@bot.command(name='resume', help='Resumes current song')
async def resume(ctx: commands.Context):
    voice_client = ctx.guild.voice_client
    if voice_client.is_connected() and voice_client.is_paused():
        voice_client.resume()
        await ctx.message.add_reaction('\u25B6')


@bot.command(name='stop', help='Stops playing song')
async def stop(ctx: commands.Context):
    global song_queue
    guild_id = ctx.guild.id
    song_queue[guild_id] = []

    voice_client = ctx.guild.voice_client
    if voice_client.is_connected() and (voice_client.is_playing() or voice_client.is_paused()):
        cleanup_ffmpeg_process(ctx, all=True)
        voice_client.stop()
        await ctx.message.add_reaction('\u23F9')


@bot.command(name='queue', help='Shows the queue')
async def view_queue(ctx: commands.Context):
    global song_queue
    song_count = 1
    song_list = ''
    guild_id = ctx.guild.id

    for song_id in song_queue.get(guild_id):
        song_list = song_list + '**' + \
            str(song_count) + '.** ' + \
            'https://www.youtube.com/watch?v=' + song_id + '\n'
        song_count += 1
    if song_list:
        await ctx.send(song_list)
    else:
        await ctx.send('**No song in queue!**')
    await ctx.message.add_reaction('\u2705')


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send('**Unknown command! Type "=help" to see all the commands**')
        await ctx.message.add_reaction('\u274C')


@tasks.loop(seconds=15)
async def afk_disconnect():
    for voice_client in bot.voice_clients:
        if voice_client.is_connected() and not voice_client.is_playing() and voice_client.channel.members == [bot.user]:
            await voice_client.disconnect()


@tasks.loop(hours=24)
async def clear_cache():
    global songs
    for file in os.listdir(SONGS_PATH):
        try:
            os.remove(SONGS_PATH + file)
        except Exception as e:
            print(e)

    songs = np.empty(0, dtype=str)


# bot.run(os.environ.get('TOKEN'))
load_dotenv(".env")
bot.run(os.getenv('TOKEN'))
