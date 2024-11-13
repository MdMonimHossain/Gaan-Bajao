import asyncio
import json
import os
import numpy as np
from dotenv import load_dotenv
from discord import (app_commands, Activity, ActivityType, Client, Embed, FFmpegOpusAudio,
                     Intents, Interaction)
from discord.ext import tasks
from youtube_search import YoutubeSearch
from yt_dlp import YoutubeDL
from logger import get_base_logger, get_ytdl_logger, setup_discord_logger


SONG_CACHE_PATH = './.song_cache/'

logger = get_base_logger()
setup_discord_logger()

song_queue = {}
song_cache = np.empty(0, dtype=str)

ytdl_options = {
    'format': 'bestaudio/best',
    'outtmpl': SONG_CACHE_PATH + '%(id)s',
    'postprocessors': [
        {
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'opus',
            'preferredquality': '128'
        }
    ],
    'logger': get_ytdl_logger(),
    'username': 'oauth',
    'password': ''
}

client = Client(intents=Intents.default())
command_tree = app_commands.CommandTree(client)


def download_song(song_id: str):
    """
    Download the song from YouTube
    """
    global song_cache
    if song_id in song_cache:
        return

    video_url = 'https://www.youtube.com/watch?v=' + song_id
    with YoutubeDL(ytdl_options) as ytdl:
        error_code = ytdl.download([video_url])
        if error_code == 0:
            song_cache = np.append(song_cache, song_id)
        else:
            logger.error(f'Error downloading song: {song_id}')


def get_song_info(search_terms: str, max_results: int = 1, lyrical_video=False):
    """
    Get the song information from YouTube.
    Adds '(Lyrics)' to the search terms if lyrical_video is True and search_terms is not a YouTube link.
    """
    if lyrical_video and 'youtube.com' not in search_terms and 'youtu.be' not in search_terms:
        search_terms = search_terms + ' (Lyrics)'

    result = YoutubeSearch(search_terms, max_results=max_results).to_json()
    json_data = json.loads(result)

    if max_results > 1:
        return json_data['videos']

    return json_data['videos'][0]


@client.event
async def on_ready():
    """
    Event triggered when the bot is ready
    """
    print(f'{client.user} is online.')
    logger.info(f'{client.user} connected to Discord.')

    await command_tree.sync()

    commands = await command_tree.fetch_commands()
    if commands:
        for command in commands:
            logger.info(f'Command registered: {command.name} - {command.id}')

    afk_disconnect.start()
    clear_cache.start()

    await client.change_presence(
        activity=Activity(type=ActivityType.listening, name='/help for help')
    )


async def disconnect_bot(interaction: Interaction):
    """
    Disconnect the bot from the voice channel
    """
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_connected():
        song_queue[interaction.guild_id] = []
        await voice_client.disconnect()
        return True
    return False


async def connect_bot(interaction: Interaction):
    """
    Connect the bot to the voice channel
    """
    if not interaction.user.voice:
        return None

    user_channel = interaction.user.voice.channel
    guild_voice_client = interaction.guild.voice_client

    if guild_voice_client in client.voice_clients:
        if guild_voice_client.channel == user_channel:
            return guild_voice_client
        await disconnect_bot(interaction)

    song_queue[interaction.guild_id] = []
    return await user_channel.connect()


@command_tree.command(name='leave')
async def leave(interaction: Interaction):
    """
    Disconnect the bot from the voice channel
    """
    was_disconnected = await disconnect_bot(interaction)
    if was_disconnected:
        await interaction.response.send_message('**Disconnected from voice channel**')
    else:
        await interaction.response.send_message('**Not connected to a voice channel**')


@command_tree.command(name='play')
async def play(interaction: Interaction, song: str):
    """
    Play song from search terms or a YouTube link

    Parameters
    ----------
    song : str
        search terms or a YouTube link
    """
    voice_client = await connect_bot(interaction)
    if voice_client is None:
        await interaction.response.send_message("**You are not connected to a voice channel**")
        return

    song_info = get_song_info(song, lyrical_video=True)
    song_title = song_info['title']
    song_id = song_info['id']
    song_queue[interaction.guild_id].append(song_id)

    if voice_client.is_playing() or voice_client.is_paused():
        await interaction.response.send_message('**Queued to play next:** ' + song_title)
        await asyncio.get_event_loop().run_in_executor(None, download_song, song_id)
        return

    try:
        song_queue[interaction.guild_id].pop(0)
        await interaction.response.send_message('**Starting to play:** ' + song_title)
        await asyncio.get_event_loop().run_in_executor(None, download_song, song_id)

        if song_id in song_cache:
            faudio: FFmpegOpusAudio = FFmpegOpusAudio(
                SONG_CACHE_PATH + song_id + '.opus', codec='copy')
            voice_client.play(faudio, after=lambda _: play_next_song(interaction))
            await interaction.edit_original_response(content='**Now playing:** ' + song_title)
        else:
            await interaction.edit_original_response(content='**Sorry! Error occured playing the song**')
            logger.error(f'Song not found in cache: {song_id}')
    except Exception as e:
        if interaction.response.is_done():
            await interaction.edit_original_response(content='**Sorry! Error occured playing the song**')
        else:
            await interaction.response.send_message('**Sorry! Error occured playing the song**')
        logger.error(e)


def play_next_song(interaction: Interaction, in_loop=False):
    """
    Play the next song in the queue
    """
    guild_id = interaction.guild_id
    voice_client = interaction.guild.voice_client

    if voice_client and voice_client.is_connected() and song_queue.get(guild_id):
        try:
            if in_loop and len(song_queue[guild_id]) > 1:
                song_id = song_queue[guild_id][1]
            else:
                song_id = song_queue[guild_id][0]
            if not in_loop or len(song_queue[guild_id]) > 1:
                song_queue[guild_id].pop(0)

            download_song(song_id)

            if song_id in song_cache:
                faudio: FFmpegOpusAudio = FFmpegOpusAudio(
                    SONG_CACHE_PATH + song_id + '.opus', codec='copy')
                voice_client.play(faudio, after=lambda _: play_next_song(interaction, in_loop))
            else:
                logger.error(f'Song not found in cache: {song_id}')

        except Exception as e:
            logger.error(e)


@command_tree.command(name='skip')
async def skip(interaction: Interaction):
    """
    Skip the current song
    """
    voice_client = interaction.guild.voice_client

    if voice_client and voice_client.is_connected() and (voice_client.is_playing() or voice_client.is_paused()):
        voice_client.stop()
        await interaction.response.send_message('**Skipped the song**')
    else:
        await interaction.response.send_message('**No song is playing**')


@command_tree.command(name='loop')
async def loop_song(interaction: Interaction, song: str):
    """
    Play song in loop from search terms or a YouTube link

    Parameters
    ----------
    song : str
        search terms or a YouTube link
    """
    voice_client = await connect_bot(interaction)
    if voice_client is None:
        await interaction.response.send_message("**You are not connected to a voice channel**")
        return
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()

    song_info = get_song_info(song, lyrical_video=True)
    song_title = song_info['title']
    song_id = song_info['id']
    song_queue[interaction.guild_id] = [song_id]

    try:
        await interaction.response.send_message(f'**Starting to play in loop:** {song_title}')
        await asyncio.get_event_loop().run_in_executor(None, download_song, song_id)

        if song_id in song_cache:
            faudio: FFmpegOpusAudio = FFmpegOpusAudio(
                SONG_CACHE_PATH + song_id + '.opus', codec='copy')
            voice_client.play(faudio, after=lambda _: play_next_song(interaction, in_loop=True))

            await interaction.edit_original_response(content=f'**Now playing in loop:** {song_title}')
        else:
            await interaction.edit_original_response(content='**Sorry! Error occured playing the song**')
            logger.error(f'Song not found in cache: {song_id}')
    except Exception as e:
        if interaction.response.is_done():
            await interaction.edit_original_response(content='**Sorry! Error occured playing the song**')
        else:
            await interaction.response.send_message('**Sorry! Error occured playing the song**')
        logger.error(e)


@command_tree.command(name='pause')
async def pause(interaction: Interaction):
    """
    Pause the current song
    """
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_connected() and voice_client.is_playing():
        voice_client.pause()
        await interaction.response.send_message('**Paused the song**')
    else:
        await interaction.response.send_message('**No song is playing**')


@command_tree.command(name='resume')
async def resume(interaction: Interaction):
    """
    Resume the paused song
    """
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_connected() and voice_client.is_paused():
        voice_client.resume()
        await interaction.response.send_message('**Resumed the song**')
    else:
        await interaction.response.send_message('**Nothing to resume**')


@command_tree.command(name='stop')
async def stop(interaction: Interaction):
    """
    Stop the current song
    """
    song_queue[interaction.guild_id] = []

    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_connected() and (voice_client.is_playing() or voice_client.is_paused()):
        voice_client.stop()
        await interaction.response.send_message('**Stopped the song**')
    else:
        await interaction.response.send_message('**No song is playing**')


@command_tree.command(name='queue')
async def view_queue(interaction: Interaction):
    """
    View the songs in the queue
    """
    song_count = 0
    song_list = ''

    await interaction.response.send_message('**Checking the queue...**')

    for i, song_id in enumerate(song_queue.get(interaction.guild_id, [])):
        song_list = song_list + '**' + str(i + 1) + '.** ' + \
            'https://www.youtube.com/watch?v=' + song_id + '\n'
        song_count += 1
    if song_list:
        song_list = '**Total ' + str(song_count) + ' song(s) in queue:**\n' + song_list
        await interaction.edit_original_response(content=song_list)
    else:
        await interaction.edit_original_response(content='**Queue is empty**')


@command_tree.command(name='search')
async def search(interaction: Interaction, query: str, max_results: int = 3):
    """
    Search for a song on YouTube

    Parameters
    ----------
    query : str
        search terms for the song
    max_results : int
        maximum number of search results to display (should be between 1 and 10)
    """
    if max_results < 1 or max_results > 10:
        await interaction.response.send_message('**Maximum results should be between 1 and 10**')
        return

    await interaction.response.send_message('**Searching for songs...**')

    song_list = get_song_info(query, max_results=max_results)

    song_info = ''
    for song in song_list:
        song_info = song_info + '**' + song['title'] + '**\n' + \
            'Duration: *' + song['duration'] + '*\n' + \
            'https://www.youtube.com/watch?v=' + song['id'] + '\n\n'

    if song_list:
        await interaction.edit_original_response(content=song_info)
    else:
        await interaction.edit_original_response(content='**No songs found**')


@command_tree.command(name='help')
async def help_message(interaction: Interaction):
    """
    Display help message
    """
    description = """
    `/play [song]`: Play a song from search terms or a YouTube link
    `/loop [song]`: Play a song in loop from search terms or a YouTube link
    `/pause`: Pause current song
    `/resume`: Resume paused song
    `/stop`: Stop current song
    `/skip`: Skip current song and play next song in the queue
    `/queue`: View the songs in queue
    `/search [query] [max_results]`: Search for a song on YouTube
    `/leave`: Disconnect from voice channel
    `/help`: Display this help message
    """

    await interaction.response.send_message(
        embed=Embed(title='Supported Commands', description=description)
    )


@tasks.loop(seconds=15)
async def afk_disconnect():
    """
    Disconnect the bot if it is alone in the voice channel
    """
    for voice_client in client.voice_clients:
        if voice_client.is_connected() and not voice_client.is_playing() and voice_client.channel.members == [client.user]:
            await voice_client.disconnect()


@tasks.loop(hours=24)
async def clear_cache():
    """
    Clear the song cache
    """
    global song_cache
    for file in os.listdir(SONG_CACHE_PATH):
        try:
            os.remove(SONG_CACHE_PATH + file)
        except Exception as e:
            logger.error(e)

    song_cache = np.empty(0, dtype=str)


# bot.run(os.environ.get('TOKEN'))
load_dotenv(".env")
client.run(os.getenv('TOKEN'), log_handler=None)
