import json
import discord
import logging
import urllib3
import os

import datetime
from discord.ext import commands
from dotenv import load_dotenv

from cogs import events

logger = logging.getLogger('discord')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)
urllib3.disable_warnings()

load_dotenv()
token = os.getenv('DISCORD_TOKEN')
ocr_token = os.getenv('OCR_TOKEN')


# noinspection PyUnusedLocal
def get_prefix(client, message):
    """Returns the prefix for the specified server"""
    if message.guild is None:
        return "!"

    with open('data/prefixes.json', 'r') as f:
        prefixes = json.load(f)

    return prefixes[str(message.guild.id)]


intents = discord.Intents.default()
intents.members = True
intents.typing = False
intents.presences = False

bot = commands.Bot(command_prefix=get_prefix, intents=intents)
bot.remove_command('help')
bot.owner_id = 196282885601361920
bot.OCR_TOKEN = ocr_token

with open('data/variables.json', 'r') as file:
    bot.maintenance_mode = json.load(file).get("maintenance_mode")

for filename in os.listdir('./cogs/'):
    if filename.endswith('.py'):
        bot.load_extension(f'cogs.{filename[:-3]}')


@bot.event
async def on_ready():
    """Wait until bot has connected to discord"""
    print("Connected to discord")

    bot.variables = {}

    # Cache variables in memory & convert ID's to objects
    build_guild_db()

    await cleanup()

    bot.warning_embed = discord.Embed(title="⚠️ Warning!", color=discord.Color.orange())
    bot.error_embed = discord.Embed(title="❌ ERROR!", color=discord.Color.red())

    bot.start_time = datetime.datetime.now()

    # Set Presence to reflect bot status
    if bot.maintenance_mode:
        await bot.change_presence(status=discord.Status.idle, activity=discord.Game("IN MAINTENANCE MODE!"))
    else:
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f"!help"))

    print(f'{bot.user.name} is now online!')


def build_guild_db():
    with open("data/variables.json", "r") as f:
        data = json.load(f)

    for g in data:
        try:
            guild = bot.get_guild(int(g))
            if guild is None:
                continue
        except ValueError:
            continue

        variables = {}
        for record in data[g]:
            if record == 'roles':
                for obj in data[g][record]:
                    try:
                        _role = guild.get_role(int(data[g][record][obj]))
                    except ValueError:
                        _role = None
                    variables[obj] = _role
            elif record == 'channels':
                for obj in data[g][record]:
                    try:
                        _channel = guild.get_channel(int(data[g][record][obj]))
                    except ValueError:
                        _channel = None
                    variables[obj] = _channel
            else:
                variables[record] = data[g][record]

        bot.variables[int(g)] = variables



async def cleanup():
    for g in bot.guilds:
        if g.id in bot.variables:
            data = bot.variables[g.id]
            # Cleanup captcha channel
            captcha_channel = data['captcha_channel']
            no_older_than = datetime.datetime.utcnow() - datetime.timedelta(days=14) + datetime.timedelta(seconds=1)
            def check(msg):
                return not msg.pinned

            await captcha_channel.purge(check=check, after=no_older_than, bulk=True)

            temprole = data['temporary_role']
            for m in temprole.members:
                if m.top_role <= temprole:
                    bot.loop.create_task(events.Events.on_member_join(events.Events(bot), m))



@bot.command(usage="load <cog>")
@commands.is_owner()
async def load(ctx, extension):
    """Load specified cog"""
    extension = extension.lower()
    bot.load_extension(f'cogs.{extension}')
    await ctx.send('{} has been loaded.'.format(extension.capitalize()))


@bot.command(usage="unload <cog>")
@commands.is_owner()
async def unload(ctx, extension):
    """Unload specified cog"""
    extension = extension.lower()
    bot.unload_extension(f'cogs.{extension}')
    await ctx.send('{} has been unloaded.'.format(extension.capitalize()))


@bot.command(usage="reload <cog/guilds/utils/all>")
@commands.is_owner()
async def reload(ctx, extension):
    """Reload specified cog"""
    extension = extension.lower()
    if extension == 'guilds':
        build_guild_db()
        extension = 'Guild Database'
    else:
        bot.reload_extension(f'cogs.{extension}')
    await ctx.send('{} has been reloaded.'.format(extension.capitalize()))


@bot.command(usage="maintenance")
@commands.is_owner()
async def maintenance(ctx):
    if bot.maintenance_mode:
        bot.maintenance_mode = False
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f"!help"))
        await ctx.send("Maintenance mode has been turned off!")
    else:
        bot.maintenance_mode = True
        await bot.change_presence(status=discord.Status.idle, activity=discord.Game("IN MAINTENANCE MODE!"))
        # with open('data/queues.pkl', 'wb') as file:
        #     pickle.dump(bot.queues, file, pickle.HIGHEST_PROTOCOL)
        #
        # print('Saved queue to file')
        await ctx.send("Maintenance mode has been turned on!")
    with open("data/variables.json", 'r+') as f:
        data = json.load(f)
        data["maintenance_mode"] = bot.maintenance_mode
        f.seek(0)
        json.dump(data, f)
        f.truncate()


@bot.check
async def maintenance_mode(ctx):
    if bot.maintenance_mode:
        if await bot.is_owner(ctx.author):
            return True
        embed = discord.Embed(title="Error!", description="Cryptographer has been put into maintenance mode by the developer! "
                                                          "This means bugs are being fixed or new features are being added.\n"
                                                          "Please be patient and if this persists for too long, contact <@196282885601361920>.",
                              color=discord.Color.orange())
        await ctx.send(embed=embed)
        return False
    return True


print("Attempting to connect to Discord")
bot.run(token)

